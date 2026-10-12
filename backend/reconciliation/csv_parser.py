"""Parsing and validation of bank statement CSV files.

This module has no database access: it turns raw bytes into validated rows and
per-row error messages so the rules can be unit tested in isolation.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

REQUIRED_COLUMNS = ("date", "description", "amount", "type", "reference")
MAX_ROWS = 10_000
MAX_AMOUNT = Decimal("99999999999999.99")


class CSVFileError(Exception):
    """The file as a whole cannot be processed (bad encoding, missing columns, empty)."""


@dataclass
class ParsedRow:
    row_number: int
    raw: dict
    transaction_date: date | None = None
    description: str = ""
    amount: Decimal | None = None
    transaction_type: str = ""
    bank_reference: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self):
        return not self.errors

    @property
    def dedupe_key(self):
        """Identity of a bank transaction for duplicate detection.

        The bank's own reference is the strongest identifier. When it is missing
        we fall back to the combination of date, amount and normalised description.
        """
        if self.bank_reference:
            return f"REF:{self.bank_reference.upper()}"
        return f"ROW:{self.transaction_date.isoformat()}|{self.amount}|{normalize_text(self.description)}"


def normalize_text(value: str) -> str:
    """Uppercase, replace punctuation with spaces and collapse whitespace."""
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", value.upper()).split())


def parse_amount(value: str) -> Decimal:
    cleaned = value.strip().replace(",", "").replace("$", "")
    if not cleaned:
        raise ValueError("Amount is required.")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Amount '{value.strip()}' is not a valid number.")
    if not amount.is_finite():
        raise ValueError(f"Amount '{value.strip()}' is not a valid number.")
    if amount.as_tuple().exponent < -2:
        raise ValueError(f"Amount '{value.strip()}' has more than 2 decimal places.")
    if abs(amount) > MAX_AMOUNT:
        raise ValueError(f"Amount '{value.strip()}' is too large.")
    return amount.quantize(Decimal("0.01"))


def parse_date(value: str) -> date:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Date is required.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        raise ValueError(f"Date '{cleaned}' must be in YYYY-MM-DD format.")
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        raise ValueError(f"Date '{cleaned}' is not a real calendar date.")


def validate_row(row_number: int, raw: dict) -> ParsedRow:
    row = ParsedRow(row_number=row_number, raw=raw)

    if raw.get(None):
        row.errors.append("Row has more columns than the header.")
    if any(raw.get(col) is None for col in REQUIRED_COLUMNS):
        row.errors.append("Row has fewer columns than the header.")
        return row

    try:
        row.transaction_date = parse_date(raw["date"])
    except ValueError as exc:
        row.errors.append(str(exc))

    row.description = " ".join(raw["description"].split())
    if not row.description:
        row.errors.append("Description is required.")
    elif len(row.description) > 500:
        row.errors.append("Description is longer than 500 characters.")

    tx_type = raw["type"].strip().upper()
    if tx_type not in ("CREDIT", "DEBIT"):
        row.errors.append(f"Type '{raw['type'].strip()}' must be 'credit' or 'debit'.")
    else:
        row.transaction_type = tx_type

    try:
        row.amount = parse_amount(raw["amount"])
    except ValueError as exc:
        row.errors.append(str(exc))
    else:
        if row.amount == 0:
            row.errors.append("Amount must not be zero.")
        elif tx_type == "CREDIT" and row.amount < 0:
            row.errors.append("Credit transactions must have a positive amount.")
        elif tx_type == "DEBIT":
            # Banks export debits either signed or unsigned; store them as negative.
            row.amount = -abs(row.amount)

    row.bank_reference = raw["reference"].strip()
    if len(row.bank_reference) > 100:
        row.errors.append("Reference is longer than 100 characters.")

    return row


def parse_statement(content: bytes) -> list[ParsedRow]:
    """Parse a whole CSV file. Raises CSVFileError for file-level problems."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CSVFileError("File must be UTF-8 encoded CSV text.")

    if not text.strip():
        raise CSVFileError("The file is empty.")

    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None:
        raise CSVFileError("The file has no header row.")
    reader.fieldnames = [(name or "").strip().lower() for name in reader.fieldnames]
    missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing:
        raise CSVFileError(f"Missing required column(s): {', '.join(missing)}.")

    rows = []
    try:
        for raw in reader:
            # Skip completely blank lines rather than reporting them as invalid.
            if all((value or "").strip() == "" for key, value in raw.items() if key is not None) and not raw.get(None):
                continue
            if len(rows) >= MAX_ROWS:
                raise CSVFileError(f"The file has more than {MAX_ROWS} rows.")
            rows.append(validate_row(reader.line_num, raw))
    except csv.Error as exc:
        raise CSVFileError(f"Malformed CSV near line {reader.line_num}: {exc}")

    if not rows:
        raise CSVFileError("The file has a header but no data rows.")
    return rows
