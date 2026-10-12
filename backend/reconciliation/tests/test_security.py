from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from reconciliation import services
from reconciliation.models import BankTransaction, CapitalCall

from .helpers import SAMPLE_CSV, api_client_for, csv_bytes, seed_bluebird, seed_northwind


class OrganizationIsolationTests(TestCase):
    def setUp(self):
        self.nw_org, self.nw_user, self.nw_calls = seed_northwind()
        self.bb_org, self.bb_user, self.bb_calls = seed_bluebird()
        self.nw = api_client_for(self.nw_user)
        self.bb = api_client_for(self.bb_user)
        self.bb_import = services.import_statement(
            organization=self.bb_org, user=self.bb_user, file_name="bluebird.csv",
            content=csv_bytes("2026-04-16,WIRE INCOMING CEDAR GROVE FUND CC-2001,40000.00,credit,FT20260416K"),
        )
        self.bb_tx = self.bb_import.transactions.get()

    def test_unauthenticated_requests_are_rejected(self):
        client = APIClient()
        for url in ["/api/me/", "/api/investors/", "/api/capital-calls/", "/api/imports/", "/api/transactions/"]:
            self.assertEqual(client.get(url).status_code, 401, url)

    def test_user_without_organization_is_forbidden(self):
        loner = get_user_model().objects.create_user("loner", password="pw-12345678")
        self.assertEqual(api_client_for(loner).get("/api/investors/").status_code, 403)
        response = APIClient().post("/api/auth/login/", {"username": "loner", "password": "pw-12345678"})
        self.assertEqual(response.status_code, 403)

    def test_login_returns_token_and_organization(self):
        response = APIClient().post("/api/auth/login/", {"username": "northwind_user", "password": "pw-12345678"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["organization"]["name"], "Northwind Ventures")
        self.assertTrue(response.data["token"])
        bad = APIClient().post("/api/auth/login/", {"username": "northwind_user", "password": "wrong"})
        self.assertEqual(bad.status_code, 400)

    def test_lists_only_show_own_organization(self):
        investors = {i["name"] for i in self.nw.get("/api/investors/").data}
        self.assertNotIn("Cedar Grove Fund", investors)
        calls = {c["reference"] for c in self.nw.get("/api/capital-calls/").data}
        self.assertEqual(calls, set(self.nw_calls))
        self.assertEqual(self.nw.get("/api/imports/").data, [])
        self.assertEqual(self.nw.get("/api/transactions/").data, [])
        self.assertEqual(self.nw.get(f"/api/transactions/?import={self.bb_import.pk}").data, [])

    def test_other_organization_objects_are_not_found(self):
        self.assertEqual(self.nw.get(f"/api/imports/{self.bb_import.pk}/").status_code, 404)
        self.assertEqual(self.nw.get(f"/api/transactions/{self.bb_tx.pk}/").status_code, 404)
        self.assertEqual(self.bb.get(f"/api/transactions/{self.bb_tx.pk}/").status_code, 200)

    def test_cannot_act_on_other_organization_transaction(self):
        for verb in ["approve", "reject", "ignore"]:
            response = self.nw.post(f"/api/transactions/{self.bb_tx.pk}/{verb}/", {}, format="json")
            self.assertEqual(response.status_code, 404, verb)
        self.bb_tx.refresh_from_db()
        self.assertEqual(self.bb_tx.status, BankTransaction.Status.SUGGESTED)
        self.assertEqual(CapitalCall.objects.get(pk=self.bb_calls["CC-2001"].pk).amount_funded, Decimal("0"))

    def test_cannot_apply_payment_to_other_organization_capital_call(self):
        nw_import = services.import_statement(
            organization=self.nw_org, user=self.nw_user, file_name="nw.csv",
            content=csv_bytes("2026-04-16,WIRE INCOMING CEDAR GROVE FUND CC-2001,40000.00,credit,FT1"),
        )
        nw_tx = nw_import.transactions.get()
        self.assertIsNone(nw_tx.suggested_capital_call)  # CC-2001 is invisible to Northwind

        response = self.nw.post(
            f"/api/transactions/{nw_tx.pk}/approve/", {"capital_call_id": self.bb_calls["CC-2001"].pk}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["detail"], "Capital call not found.")
        self.assertEqual(CapitalCall.objects.get(pk=self.bb_calls["CC-2001"].pk).amount_funded, Decimal("0"))

    def test_duplicate_detection_is_scoped_per_organization(self):
        bb_upload = self.bb.post(
            "/api/imports/", {"file": SimpleUploadedFile("s.csv", SAMPLE_CSV)}, format="multipart"
        )
        nw_upload = self.nw.post(
            "/api/imports/", {"file": SimpleUploadedFile("s.csv", SAMPLE_CSV)}, format="multipart"
        )
        # Bluebird already imported FT20260416K earlier, so only that row is a cross-import duplicate there.
        self.assertEqual(bb_upload.data["duplicate_rows"], 2)
        self.assertEqual(nw_upload.data["duplicate_rows"], 1)
        self.assertEqual(nw_upload.data["imported_rows"], 11)
