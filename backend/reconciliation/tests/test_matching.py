from datetime import date
from decimal import Decimal

from django.test import TestCase

from reconciliation.matching import Matcher, extract_call_reference, investor_match_key

from .helpers import make_call, make_org

D = Decimal
APRIL_10 = date(2026, 4, 10)


class HelperTests(TestCase):
    def test_extract_call_reference_variants(self):
        self.assertEqual(extract_call_reference("WIRE REF CC-1002"), "CC-1002")
        self.assertEqual(extract_call_reference("ach credit haller cc1001"), "CC-1001")
        self.assertEqual(extract_call_reference("CC 1003 payment"), "CC-1003")
        self.assertIsNone(extract_call_reference("ACCOUNT 1001"))
        self.assertIsNone(extract_call_reference("UNKNOWN INCOMING WIRE"))

    def test_investor_match_key_strips_legal_suffix(self):
        self.assertEqual(investor_match_key("Haller Capital LLC"), "HALLER CAPITAL")
        self.assertEqual(investor_match_key("Acme Partners, Ltd."), "ACME PARTNERS")
        self.assertEqual(investor_match_key("LLC"), "LLC")


class MatcherTests(TestCase):
    def setUp(self):
        self.org, _ = make_org("Northwind Ventures", "northwind")
        self.haller = make_call(self.org, "Haller Capital LLC", "CC-1001", "20000.00")
        self.patel = make_call(self.org, "Patel Family Trust", "CC-1003", "25000.00")
        self.meridian = make_call(self.org, "Meridian Partners", "CC-1004", "15000.00")

    def match(self, description, amount, when=APRIL_10, matcher=None):
        return (matcher or Matcher(self.org)).match(description, "FT1", D(amount), when)

    def test_reference_name_and_exact_amount_is_confident(self):
        result = self.match("ACH CREDIT HALLER CAPITAL LLC CC-1001", "20000.00")
        self.assertTrue(result.is_confident)
        self.assertEqual(result.confidence, 100)
        self.assertEqual(result.capital_call, self.haller)

    def test_reference_without_dash_and_name_without_suffix(self):
        result = self.match("ACH CREDIT HALLER CAPITAL cc1001", "5000.00")
        self.assertEqual(result.capital_call, self.haller)
        self.assertEqual(result.confidence, 80)
        self.assertTrue(result.is_confident)

    def test_name_and_exact_amount_without_reference_is_confident(self):
        result = self.match("  wire incoming meridian partners  ", "15000.00")
        self.assertTrue(result.is_confident)
        self.assertEqual(result.capital_call, self.meridian)
        self.assertEqual(result.confidence, 60)

    def test_name_only_partial_payment_needs_review(self):
        result = self.match("WIRE INCOMING PATEL FAMILY TRUST", "12500.00")
        self.assertFalse(result.is_confident)
        self.assertEqual(result.capital_call, self.patel)  # kept as a candidate for the reviewer
        self.assertIn("Low confidence", result.review_reasons[0])

    def test_unknown_payer_needs_review(self):
        result = self.match("UNKNOWN INCOMING WIRE", "9999.99")
        self.assertFalse(result.is_confident)
        self.assertIsNone(result.capital_call)
        self.assertEqual(result.review_reasons, ["No capital call reference or known investor name found."])

    def test_amount_larger_than_balance_needs_review(self):
        result = self.match("WIRE PATEL FAMILY TRUST CC-1003", "30000.00")
        self.assertFalse(result.is_confident)
        self.assertIn("exceeds the available balance", result.review_reasons[0])

    def test_reference_and_name_conflict_needs_review(self):
        result = self.match("WIRE MERIDIAN PARTNERS CC-1001", "20000.00")
        self.assertFalse(result.is_confident)
        self.assertIn("conflicts with CC-1001", result.review_reasons[0])

    def test_payment_before_call_date_needs_review(self):
        result = self.match("WIRE HALLER CAPITAL CC-1001", "20000.00", when=date(2026, 3, 20))
        self.assertFalse(result.is_confident)
        self.assertIn("before CC-1001 was issued", result.review_reasons[0])

    def test_reference_from_another_organization_is_not_found(self):
        other, _ = make_org("Bluebird Capital", "bluebird")
        make_call(other, "Cedar Grove Fund", "CC-2001", "40000.00")
        result = self.match("WIRE INCOMING CEDAR GROVE FUND CC-2001", "40000.00")
        self.assertIsNone(result.capital_call)
        self.assertIn("CC-2001 was not found for this organization", result.review_reasons[0])

    def test_multiple_open_calls_resolved_by_exact_amount(self):
        second = make_call(self.org, "Haller Capital LLC", "CC-1007", "7500.00")
        result = self.match("WIRE HALLER CAPITAL", "7500.00")
        self.assertEqual(result.capital_call, second)
        self.assertTrue(result.is_confident)

    def test_multiple_open_calls_without_exact_amount_needs_review(self):
        make_call(self.org, "Haller Capital LLC", "CC-1007", "7500.00")
        result = self.match("WIRE HALLER CAPITAL", "1000.00")
        self.assertIsNone(result.capital_call)
        self.assertIn("2 open capital calls", result.review_reasons[0])

    def test_fully_funded_calls_are_not_candidates(self):
        org2, _ = make_org("Other", "other")
        make_call(org2, "Oakridge Holdings LLC", "CC-1", "10000.00", call_date=date(2026, 1, 1), funded="10000.00")
        open_call = make_call(org2, "Oakridge Holdings LLC", "CC-2", "15000.00")
        result = Matcher(org2).match("WIRE OAKRIDGE HOLDINGS LLC", "FT", D("15000.00"), APRIL_10)
        self.assertEqual(result.capital_call, open_call)

    def test_reservations_prevent_double_suggestion_in_one_batch(self):
        matcher = Matcher(self.org)
        first = self.match("HALLER CAPITAL CC-1001", "20000.00", matcher=matcher)
        matcher.reserve(first, D("20000.00"))
        second = self.match("HALLER CAPITAL CC-1001", "7500.00", matcher=matcher)
        self.assertTrue(first.is_confident)
        self.assertFalse(second.is_confident)
        self.assertIn("already earmarked", second.review_reasons[0])
