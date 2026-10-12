from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from reconciliation.csv_parser import CSVFileError, parse_statement

from .helpers import SAMPLE_CSV, csv_bytes


class ParseStatementTests(SimpleTestCase):
    def test_valid_row_is_normalised(self):
        [row] = parse_statement(csv_bytes('2026-04-08,"  wire incoming   meridian partners  ","15,000.00",CREDIT,FT1'))
        self.assertTrue(row.is_valid)
        self.assertEqual(row.transaction_date, date(2026, 4, 8))
        self.assertEqual(row.description, "wire incoming meridian partners")
        self.assertEqual(row.amount, Decimal("15000.00"))
        self.assertEqual(row.transaction_type, "CREDIT")
        self.assertEqual(row.bank_reference, "FT1")
        self.assertEqual(row.row_number, 2)  # line 1 is the header

    def test_debit_amount_is_stored_negative(self):
        rows = parse_statement(csv_bytes("2026-04-05,FEE,-25.00,debit,F1", "2026-04-05,FEE,25.00,debit,F2"))
        self.assertEqual([r.amount for r in rows], [Decimal("-25.00"), Decimal("-25.00")])
        self.assertTrue(all(r.is_valid for r in rows))

    def test_invalid_calendar_date(self):
        [row] = parse_statement(csv_bytes("2026-04-31,WIRE,500.00,credit,R1"))
        self.assertFalse(row.is_valid)
        self.assertIn("not a real calendar date", row.errors[0])

    def test_wrong_date_format(self):
        [row] = parse_statement(csv_bytes("04/03/2026,WIRE,500.00,credit,R1"))
        self.assertIn("YYYY-MM-DD", row.errors[0])

    def test_negative_credit_is_invalid(self):
        [row] = parse_statement(csv_bytes("2026-04-17,ACH CREDIT,-15000.00,credit,R1"))
        self.assertEqual(row.errors, ["Credit transactions must have a positive amount."])

    def test_bad_amounts(self):
        rows = parse_statement(csv_bytes(
            "2026-04-01,A,abc,credit,R1",
            "2026-04-01,B,0,credit,R2",
            "2026-04-01,C,10.555,credit,R3",
            "2026-04-01,D,,credit,R4",
        ))
        self.assertIn("not a valid number", rows[0].errors[0])
        self.assertIn("must not be zero", rows[1].errors[0])
        self.assertIn("more than 2 decimal places", rows[2].errors[0])
        self.assertIn("Amount is required", rows[3].errors[0])

    def test_unknown_type_and_missing_description(self):
        [row] = parse_statement(csv_bytes("2026-04-01,,100.00,transfer,R1"))
        self.assertIn("Description is required.", row.errors)
        self.assertTrue(any("must be 'credit' or 'debit'" in e for e in row.errors))

    def test_column_count_mismatch(self):
        rows = parse_statement(csv_bytes("2026-04-01,A,100.00,credit,R1,extra", "2026-04-01,A,100.00"))
        self.assertIn("Row has more columns than the header.", rows[0].errors)
        self.assertIn("Row has fewer columns than the header.", rows[1].errors)

    def test_blank_lines_are_skipped(self):
        rows = parse_statement(csv_bytes("2026-04-01,A,100.00,credit,R1", "", ",,,,", "2026-04-02,B,1.00,credit,R2"))
        self.assertEqual(len(rows), 2)

    def test_header_is_case_and_whitespace_insensitive_and_bom_tolerant(self):
        content = "﻿ Date ,DESCRIPTION,Amount,Type,Reference\n2026-04-01,A,1.00,credit,R1\n".encode("utf-8")
        [row] = parse_statement(content)
        self.assertTrue(row.is_valid)

    def test_missing_columns_rejects_file(self):
        with self.assertRaisesMessage(CSVFileError, "Missing required column(s): type, reference"):
            parse_statement(b"date,description,amount\n2026-04-01,A,1.00\n")

    def test_empty_and_header_only_files(self):
        with self.assertRaisesMessage(CSVFileError, "empty"):
            parse_statement(b"   ")
        with self.assertRaisesMessage(CSVFileError, "no data rows"):
            parse_statement(HEADER_ONLY)

    def test_non_utf8_file(self):
        with self.assertRaisesMessage(CSVFileError, "UTF-8"):
            parse_statement(b"\xff\xfe\x00d\x00a")

    def test_dedupe_key_prefers_bank_reference(self):
        rows = parse_statement(csv_bytes("2026-04-01,Wire A,1.00,credit,ft1", "2026-04-01,Wire  a!,1.00,credit,"))
        self.assertEqual(rows[0].dedupe_key, "REF:FT1")
        self.assertEqual(rows[1].dedupe_key, "ROW:2026-04-01|1.00|WIRE A")

    def test_sample_statement(self):
        rows = parse_statement(SAMPLE_CSV)
        self.assertEqual(len(rows), 14)
        invalid = {r.row_number: r.errors for r in rows if not r.is_valid}
        self.assertEqual(set(invalid), {13, 14})


HEADER_ONLY = b"date,description,amount,type,reference\n"
