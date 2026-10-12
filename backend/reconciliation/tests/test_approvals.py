from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from reconciliation import services
from reconciliation.models import BankTransaction, CapitalCall, Payment

from .helpers import api_client_for, csv_bytes, seed_northwind

S = BankTransaction.Status


class ApprovalTests(TestCase):
    def setUp(self):
        self.org, self.user, self.calls = seed_northwind()
        self.client = api_client_for(self.user)
        statement = services.import_statement(
            organization=self.org, user=self.user, file_name="s.csv",
            content=csv_bytes(
                "2026-04-03,WIRE RAHUL SHAH TRUST REF CC-1002,25000.00,credit,T1",
                "2026-04-07,WIRE INCOMING PATEL FAMILY TRUST,12500.00,credit,T2",
                "2026-04-09,UNKNOWN INCOMING WIRE,9999.99,credit,T3",
                "2026-04-15,WIRE INCOMING PATEL FAMILY TRUST CC-1003,13000.00,credit,T4",
                "2026-04-05,BANK FEE,-25.00,debit,T5",
            ),
        )
        self.tx = {t.bank_reference: t for t in statement.transactions.all()}

    def action(self, ref, verb, **data):
        return self.client.post(f"/api/transactions/{self.tx[ref].pk}/{verb}/", data, format="json")

    def call(self, reference):
        return CapitalCall.objects.get(organization=self.org, reference=reference)

    def test_approve_updates_funded_remaining_and_status(self):
        response = self.action("T1", "approve")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], S.APPROVED)
        self.assertEqual(response.data["reviewed_by"], self.user.username)

        call = self.call("CC-1002")
        self.assertEqual(call.amount_funded, Decimal("25000.00"))
        self.assertEqual(call.remaining_amount, Decimal("0.00"))
        self.assertEqual(call.status, CapitalCall.Status.FUNDED)
        self.assertEqual(Payment.objects.get().amount, Decimal("25000.00"))

        investors = {i["name"]: i for i in self.client.get("/api/investors/").data}
        self.assertEqual(investors["Rahul Shah Trust"]["total_funded"], "25000.00")
        self.assertEqual(investors["Rahul Shah Trust"]["remaining_balance"], "0.00")
        self.assertEqual(investors["Rahul Shah Trust"]["payment_status"], "FUNDED")

    def test_partial_payment_sets_partially_funded(self):
        response = self.action("T2", "approve")  # needs-review item approved with its suggested call
        self.assertEqual(response.status_code, 200, response.data)
        call = self.call("CC-1003")
        self.assertEqual(call.status, CapitalCall.Status.PARTIALLY_FUNDED)
        self.assertEqual(call.remaining_amount, Decimal("12500.00"))

    def test_double_approval_is_rejected_and_does_not_double_fund(self):
        self.assertEqual(self.action("T1", "approve").status_code, 200)
        response = self.action("T1", "approve")
        self.assertEqual(response.status_code, 409)
        self.assertIn("already been approved", response.data["detail"])
        self.assertEqual(self.call("CC-1002").amount_funded, Decimal("25000.00"))
        self.assertEqual(Payment.objects.count(), 1)

    def test_over_funding_is_blocked(self):
        self.assertEqual(self.action("T2", "approve").status_code, 200)
        response = self.action("T4", "approve")  # 13,000 against 12,500 remaining
        self.assertEqual(response.status_code, 409)
        self.assertIn("over-fund", response.data["detail"])
        call = self.call("CC-1003")
        self.assertEqual(call.amount_funded, Decimal("12500.00"))
        self.tx["T4"].refresh_from_db()
        self.assertEqual(self.tx["T4"].status, S.NEEDS_REVIEW)

    def test_approve_unmatched_item_requires_a_capital_call(self):
        response = self.action("T3", "approve")
        self.assertEqual(response.status_code, 409)
        self.assertIn("Choose a capital call", response.data["detail"])

        response = self.action("T3", "approve", capital_call_id=self.calls["CC-1004"].pk, note="Confirmed by phone")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["suggested_capital_call_reference"], "CC-1004")
        self.assertEqual(response.data["review_note"], "Confirmed by phone")
        self.assertEqual(self.call("CC-1004").amount_funded, Decimal("9999.99"))

    def test_reject_then_approve_needs_explicit_call(self):
        self.assertEqual(self.action("T2", "reject").status_code, 200)
        self.tx["T2"].refresh_from_db()
        self.assertEqual(self.tx["T2"].status, S.REJECTED)
        self.assertEqual(self.action("T2", "approve").status_code, 409)
        self.assertEqual(self.action("T2", "reject").status_code, 409)
        response = self.action("T2", "approve", capital_call_id=self.calls["CC-1003"].pk)
        self.assertEqual(response.status_code, 200)

    def test_ignore(self):
        response = self.action("T3", "ignore", note="Refund from vendor")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], S.IGNORED)
        self.assertEqual(self.action("T3", "approve", capital_call_id=self.calls["CC-1004"].pk).status_code, 409)

    def test_approved_transaction_cannot_be_rejected_or_ignored(self):
        self.action("T1", "approve")
        self.assertEqual(self.action("T1", "reject").status_code, 409)
        self.assertEqual(self.action("T1", "ignore").status_code, 409)

    def test_debit_cannot_fund_a_call(self):
        self.assertEqual(self.tx["T5"].status, S.IGNORED)
        response = self.action("T5", "approve", capital_call_id=self.calls["CC-1004"].pk)
        self.assertEqual(response.status_code, 409)

    def test_database_prevents_second_payment_for_same_transaction(self):
        self.action("T1", "approve")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                organization=self.org, capital_call=self.call("CC-1002"), bank_transaction=self.tx["T1"],
                amount=Decimal("1.00"), approved_by=self.user,
            )

    def test_database_prevents_funded_above_called(self):
        call = self.call("CC-1002")
        call.amount_funded = call.amount_called + 1
        with self.assertRaises(IntegrityError), transaction.atomic():
            call.save()

    def test_transaction_list_filters_by_status(self):
        response = self.client.get("/api/transactions/?status=needs_review")
        self.assertEqual({t["bank_reference"] for t in response.data}, {"T2", "T3", "T4"})
