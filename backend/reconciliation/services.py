"""Business operations. Every write runs inside a database transaction."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .csv_parser import parse_statement
from .matching import Matcher
from .models import (
    BankTransaction,
    CapitalCall,
    ImportRowIssue,
    Organization,
    Payment,
    StatementImport,
)

Status = BankTransaction.Status

# Statuses from which a reviewer may still act on a transaction.
APPROVABLE = {Status.SUGGESTED, Status.NEEDS_REVIEW, Status.REJECTED}
REJECTABLE = {Status.SUGGESTED, Status.NEEDS_REVIEW}
IGNORABLE = {Status.SUGGESTED, Status.NEEDS_REVIEW, Status.REJECTED}


class ReconciliationError(Exception):
    """A business rule prevented the requested operation."""


def _raw_for_storage(raw: dict) -> dict:
    return {("_extra" if key is None else key): value for key, value in raw.items()}


def _pending_reservations(organization) -> dict[int, Decimal]:
    """Amounts already earmarked by unreviewed suggestions from earlier imports."""
    rows = (
        BankTransaction.objects.filter(
            organization=organization,
            status__in=[Status.SUGGESTED, Status.NEEDS_REVIEW],
            suggested_capital_call__isnull=False,
        )
        .values("suggested_capital_call_id")
        .annotate(total=Sum("amount"))
    )
    return {row["suggested_capital_call_id"]: row["total"] for row in rows}


def import_statement(*, organization, user, file_name: str, content: bytes) -> StatementImport:
    """Validate a CSV file, store valid non-duplicate rows and suggest matches.

    Raises CSVFileError if the file itself cannot be processed; in that case
    nothing is written.
    """
    rows = parse_statement(content)

    with transaction.atomic():
        # Serialise imports per organization so concurrent uploads of the same
        # file cannot both pass the duplicate check.
        Organization.objects.select_for_update().get(pk=organization.pk)

        statement = StatementImport.objects.create(
            organization=organization, uploaded_by=user, file_name=file_name[:255], total_rows=len(rows)
        )

        valid_rows = [row for row in rows if row.is_valid]
        existing = {
            tx.dedupe_key: tx
            for tx in BankTransaction.objects.filter(
                organization=organization, dedupe_key__in=[row.dedupe_key for row in valid_rows]
            )
        }

        issues = []
        seen_in_file = {}
        to_create = []
        for row in rows:
            if not row.is_valid:
                issues.append(ImportRowIssue(
                    statement_import=statement, row_number=row.row_number,
                    issue_type=ImportRowIssue.IssueType.INVALID,
                    messages=row.errors, raw_data=_raw_for_storage(row.raw),
                ))
                continue
            key = row.dedupe_key
            if key in seen_in_file:
                message = f"Duplicate of row {seen_in_file[key]} in this file."
            elif key in existing:
                prior = existing[key]
                message = (
                    f"Already imported in import #{prior.statement_import_id} "
                    f"(row {prior.row_number}, {prior.transaction_date}, {prior.amount:,.2f})."
                )
            else:
                seen_in_file[key] = row.row_number
                to_create.append(row)
                continue
            issues.append(ImportRowIssue(
                statement_import=statement, row_number=row.row_number,
                issue_type=ImportRowIssue.IssueType.DUPLICATE,
                messages=[message], raw_data=_raw_for_storage(row.raw),
            ))

        matcher = Matcher(organization, reserved=_pending_reservations(organization))
        transactions = []
        for row in to_create:
            tx = BankTransaction(
                organization=organization, statement_import=statement, row_number=row.row_number,
                transaction_date=row.transaction_date, description=row.description, amount=row.amount,
                transaction_type=row.transaction_type, bank_reference=row.bank_reference,
                dedupe_key=row.dedupe_key,
            )
            if row.transaction_type == BankTransaction.Type.DEBIT:
                tx.status = Status.IGNORED
                tx.review_reasons = ["Debit transaction; not a capital call receipt."]
            else:
                result = matcher.match(row.description, row.bank_reference, row.amount, row.transaction_date)
                matcher.reserve(result, row.amount)
                tx.status = Status.SUGGESTED if result.is_confident else Status.NEEDS_REVIEW
                tx.suggested_investor = result.investor
                tx.suggested_capital_call = result.capital_call
                tx.confidence = result.confidence
                tx.match_reasons = result.reasons
                tx.review_reasons = result.review_reasons
            transactions.append(tx)

        BankTransaction.objects.bulk_create(transactions)
        ImportRowIssue.objects.bulk_create(issues)

        statement.imported_rows = len(transactions)
        statement.invalid_rows = sum(1 for i in issues if i.issue_type == ImportRowIssue.IssueType.INVALID)
        statement.duplicate_rows = sum(1 for i in issues if i.issue_type == ImportRowIssue.IssueType.DUPLICATE)
        statement.suggested_matches = sum(1 for t in transactions if t.status == Status.SUGGESTED)
        statement.needs_review = sum(1 for t in transactions if t.status == Status.NEEDS_REVIEW)
        statement.ignored_rows = sum(1 for t in transactions if t.status == Status.IGNORED)
        statement.save()

    return statement


def _lock_transaction(organization, transaction_id) -> BankTransaction:
    """Lock a transaction row, scoped to the organization (raises DoesNotExist otherwise)."""
    return BankTransaction.objects.select_for_update().get(pk=transaction_id, organization=organization)


def _mark_reviewed(tx, user, status, note=""):
    tx.status = status
    tx.reviewed_by = user
    tx.reviewed_at = timezone.now()
    tx.review_note = note[:500]


@transaction.atomic
def approve_transaction(*, organization, user, transaction_id, capital_call_id=None, note="") -> BankTransaction:
    tx = _lock_transaction(organization, transaction_id)
    if tx.status == Status.APPROVED:
        raise ReconciliationError("This transaction has already been approved.")
    if tx.status not in APPROVABLE:
        raise ReconciliationError(f"A transaction with status {tx.get_status_display()} cannot be approved.")
    if tx.transaction_type != BankTransaction.Type.CREDIT or tx.amount <= 0:
        raise ReconciliationError("Only incoming credit transactions can fund a capital call.")

    # Once a suggestion has been rejected, the reviewer must pick the call explicitly.
    call_id = capital_call_id or (tx.suggested_capital_call_id if tx.status != Status.REJECTED else None)
    if call_id is None:
        raise ReconciliationError("Choose a capital call to apply this payment to.")
    try:
        call = CapitalCall.objects.select_for_update().get(pk=call_id, organization=organization)
    except CapitalCall.DoesNotExist:
        raise ReconciliationError("Capital call not found.")

    if tx.amount > call.remaining_amount:
        raise ReconciliationError(
            f"Payment of {tx.amount:,.2f} exceeds the outstanding balance of {call.remaining_amount:,.2f} "
            f"on {call.reference}; approving it would over-fund the call."
        )

    Payment.objects.create(
        organization=organization, capital_call=call, bank_transaction=tx, amount=tx.amount, approved_by=user
    )
    call.amount_funded += tx.amount
    call.refresh_status()
    call.save(update_fields=["amount_funded", "status"])

    tx.suggested_capital_call = call
    tx.suggested_investor = call.investor
    _mark_reviewed(tx, user, Status.APPROVED, note)
    tx.save()
    return tx


@transaction.atomic
def reject_transaction(*, organization, user, transaction_id, note="") -> BankTransaction:
    tx = _lock_transaction(organization, transaction_id)
    if tx.status not in REJECTABLE:
        raise ReconciliationError(f"A transaction with status {tx.get_status_display()} cannot be rejected.")
    _mark_reviewed(tx, user, Status.REJECTED, note)
    tx.save()
    return tx


@transaction.atomic
def ignore_transaction(*, organization, user, transaction_id, note="") -> BankTransaction:
    tx = _lock_transaction(organization, transaction_id)
    if tx.status not in IGNORABLE:
        raise ReconciliationError(f"A transaction with status {tx.get_status_display()} cannot be ignored.")
    _mark_reviewed(tx, user, Status.IGNORED, note)
    tx.save()
    return tx
