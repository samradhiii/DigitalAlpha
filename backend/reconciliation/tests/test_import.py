from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from reconciliation import services
from reconciliation.csv_parser import CSVFileError
from reconciliation.models import BankTransaction, ImportRowIssue, StatementImport

from .helpers import SAMPLE_CSV, api_client_for, csv_bytes, seed_northwind

S = BankTransaction.Status


class ImportStatementTests(TestCase):
    def setUp(self):
        self.org, self.user, self.calls = seed_northwind()

    def run_import(self, content, name="statement.csv"):
        return services.import_statement(organization=self.org, user=self.user, file_name=name, content=content)

    def test_sample_statement_summary(self):
        statement = self.run_import(SAMPLE_CSV)
        self.assertEqual(statement.total_rows, 14)
        self.assertEqual(statement.invalid_rows, 2)
        self.assertEqual(statement.duplicate_rows, 1)
        self.assertEqual(statement.imported_rows, 11)
        self.assertEqual(statement.suggested_matches, 4)
        self.assertEqual(statement.needs_review, 6)
        self.assertEqual(statement.ignored_rows, 1)

        by_line = {tx.row_number: tx for tx in statement.transactions.all()}
        expected = {
            2: (S.SUGGESTED, "CC-1002"),     # Rahul Shah Trust, reference + name + exact amount
            3: (S.SUGGESTED, "CC-1001"),     # Haller Capital, exact
            4: (S.IGNORED, None),            # bank fee (debit)
            5: (S.NEEDS_REVIEW, "CC-1003"),  # Patel, name only, partial
            6: (S.SUGGESTED, "CC-1004"),     # Meridian, messy whitespace/case, exact amount
            7: (S.NEEDS_REVIEW, None),       # unknown payer
            8: (S.SUGGESTED, "CC-1006"),     # Oakridge, name + exact (CC-1005 already funded)
            9: (S.NEEDS_REVIEW, "CC-1001"),  # Haller second payment would over-fund
            10: (S.NEEDS_REVIEW, "CC-1003"),  # Patel second payment would over-fund
            12: (S.NEEDS_REVIEW, None),      # CC-2001 belongs to another organization
            15: (S.NEEDS_REVIEW, "CC-1006"),  # before call date and would over-fund
        }
        for line, (status, reference) in expected.items():
            tx = by_line[line]
            self.assertEqual(tx.status, status, f"line {line}")
            self.assertEqual(getattr(tx.suggested_capital_call, "reference", None), reference, f"line {line}")

        issues = {i.row_number: i for i in statement.issues.all()}
        self.assertEqual(issues[11].issue_type, ImportRowIssue.IssueType.DUPLICATE)
        self.assertEqual(issues[11].messages, ["Duplicate of row 2 in this file."])
        self.assertEqual(issues[13].issue_type, ImportRowIssue.IssueType.INVALID)
        self.assertEqual(issues[14].issue_type, ImportRowIssue.IssueType.INVALID)
        self.assertEqual(issues[13].raw_data["date"], "2026-04-31")

    def test_reimporting_same_file_marks_every_valid_row_duplicate(self):
        self.run_import(SAMPLE_CSV)
        second = self.run_import(SAMPLE_CSV)
        self.assertEqual(second.imported_rows, 0)
        self.assertEqual(second.duplicate_rows, 12)
        self.assertEqual(second.invalid_rows, 2)
        self.assertEqual(BankTransaction.objects.filter(organization=self.org).count(), 11)
        message = second.issues.filter(row_number=2).get().messages[0]
        self.assertIn("Already imported in import #", message)

    def test_duplicate_without_bank_reference_uses_date_amount_description(self):
        statement = self.run_import(csv_bytes(
            "2026-04-03,WIRE RAHUL SHAH TRUST,100.00,credit,",
            "2026-04-03,  wire rahul shah trust ,100.00,CREDIT,",
            "2026-04-03,WIRE RAHUL SHAH TRUST,100.01,credit,",
        ))
        self.assertEqual(statement.imported_rows, 2)
        self.assertEqual(statement.duplicate_rows, 1)

    def test_pending_suggestions_from_earlier_import_reserve_balance(self):
        self.run_import(csv_bytes("2026-04-04,HALLER CAPITAL CC-1001,20000.00,credit,A1"))
        later = self.run_import(csv_bytes("2026-04-05,HALLER CAPITAL CC-1001,20000.00,credit,A2"))
        tx = later.transactions.get()
        self.assertEqual(tx.status, S.NEEDS_REVIEW)
        self.assertIn("already earmarked", tx.review_reasons[0])

    def test_file_level_error_writes_nothing(self):
        with self.assertRaises(CSVFileError):
            self.run_import(b"date,amount\n2026-04-01,5\n")
        self.assertFalse(StatementImport.objects.exists())

    def test_upload_endpoint(self):
        client = api_client_for(self.user)
        response = client.post(
            "/api/imports/", {"file": SimpleUploadedFile("bank.csv", SAMPLE_CSV, "text/csv")}, format="multipart"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["imported_rows"], 11)
        self.assertEqual(len(response.data["issues"]), 3)
        self.assertEqual(len(response.data["transactions"]), 11)

    def test_upload_endpoint_rejects_bad_files(self):
        client = api_client_for(self.user)
        cases = [
            (SimpleUploadedFile("bank.txt", SAMPLE_CSV), "Please upload a .csv file."),
            (SimpleUploadedFile("bank.csv", b"foo,bar\n1,2\n"), "Missing required column(s)"),
        ]
        for upload, message in cases:
            response = client.post("/api/imports/", {"file": upload}, format="multipart")
            self.assertEqual(response.status_code, 400)
            self.assertIn(message, response.data["detail"])
        response = client.post("/api/imports/", {}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)
