from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Organization(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Membership(models.Model):
    """Links a user to exactly one organization. All data access is scoped through it."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")

    def __str__(self):
        return f"{self.user} @ {self.organization}"


class Investor(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="investors")
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="uniq_investor_name_per_org"),
        ]

    def __str__(self):
        return self.name


class CapitalCall(models.Model):
    """A capital call notice issued to one investor, identified by a reference such as CC-1001."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PARTIALLY_FUNDED = "PARTIALLY_FUNDED", "Partially funded"
        FUNDED = "FUNDED", "Funded"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="capital_calls")
    investor = models.ForeignKey(Investor, on_delete=models.PROTECT, related_name="capital_calls")
    reference = models.CharField(max_length=50)
    call_date = models.DateField()
    due_date = models.DateField()
    amount_called = models.DecimalField(max_digits=16, decimal_places=2)
    amount_funded = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["call_date", "reference"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "reference"], name="uniq_call_reference_per_org"),
            models.CheckConstraint(condition=Q(amount_called__gt=0), name="call_amount_positive"),
            models.CheckConstraint(
                condition=Q(amount_funded__gte=0) & Q(amount_funded__lte=models.F("amount_called")),
                name="call_funded_within_called",
            ),
        ]

    def __str__(self):
        return f"{self.reference} ({self.investor})"

    @property
    def remaining_amount(self):
        return self.amount_called - self.amount_funded

    def refresh_status(self):
        if self.amount_funded <= 0:
            self.status = self.Status.PENDING
        elif self.amount_funded < self.amount_called:
            self.status = self.Status.PARTIALLY_FUNDED
        else:
            self.status = self.Status.FUNDED

    def clean(self):
        if self.investor_id and self.organization_id and self.investor.organization_id != self.organization_id:
            raise ValidationError("Investor must belong to the same organization as the capital call.")


class StatementImport(models.Model):
    """One uploaded bank statement file and its import summary counts."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="imports")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    file_name = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    total_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    suggested_matches = models.PositiveIntegerField(default=0)
    needs_review = models.PositiveIntegerField(default=0)
    ignored_rows = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return f"{self.file_name} ({self.organization})"


class ImportRowIssue(models.Model):
    """A CSV row that was not imported, either because it failed validation or was a duplicate."""

    class IssueType(models.TextChoices):
        INVALID = "INVALID", "Invalid"
        DUPLICATE = "DUPLICATE", "Duplicate"

    statement_import = models.ForeignKey(StatementImport, on_delete=models.CASCADE, related_name="issues")
    row_number = models.PositiveIntegerField()
    issue_type = models.CharField(max_length=20, choices=IssueType.choices)
    messages = models.JSONField(default=list)
    raw_data = models.JSONField(default=dict)

    class Meta:
        ordering = ["row_number"]


class BankTransaction(models.Model):
    class Type(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    class Status(models.TextChoices):
        SUGGESTED = "SUGGESTED", "Suggested match"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs manual review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        IGNORED = "IGNORED", "Ignored"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="transactions")
    statement_import = models.ForeignKey(StatementImport, on_delete=models.CASCADE, related_name="transactions")
    row_number = models.PositiveIntegerField()
    transaction_date = models.DateField()
    description = models.CharField(max_length=500)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=Type.choices)
    bank_reference = models.CharField(max_length=100, blank=True)
    # Identity used for duplicate detection; unique per organization so the same
    # bank transaction can never be imported (and therefore funded) twice.
    dedupe_key = models.CharField(max_length=300)

    status = models.CharField(max_length=20, choices=Status.choices)
    suggested_investor = models.ForeignKey(
        Investor, on_delete=models.SET_NULL, null=True, blank=True, related_name="suggested_transactions"
    )
    suggested_capital_call = models.ForeignKey(
        CapitalCall, on_delete=models.SET_NULL, null=True, blank=True, related_name="suggested_transactions"
    )
    confidence = models.PositiveSmallIntegerField(default=0)
    match_reasons = models.JSONField(default=list)
    review_reasons = models.JSONField(default=list)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["transaction_date", "id"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "dedupe_key"], name="uniq_transaction_per_org"),
        ]

    def __str__(self):
        return f"{self.transaction_date} {self.amount} {self.description}"


class Payment(models.Model):
    """An approved application of a bank transaction to a capital call.

    The one-to-one link to BankTransaction guarantees at database level that a
    transaction can fund at most one capital call, exactly once.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="payments")
    capital_call = models.ForeignKey(CapitalCall, on_delete=models.PROTECT, related_name="payments")
    bank_transaction = models.OneToOneField(BankTransaction, on_delete=models.PROTECT, related_name="payment")
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    approved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-approved_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
        ]
