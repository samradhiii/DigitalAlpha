from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from reconciliation.models import CapitalCall, Investor, Membership, Organization

SAMPLE_CSV = (Path(__file__).parent / "fixtures" / "sample_bank_statement.csv").read_bytes()
HEADER = "date,description,amount,type,reference\n"


def csv_bytes(*lines: str) -> bytes:
    return (HEADER + "\n".join(lines) + "\n").encode()


def make_org(name, slug, username=None):
    org = Organization.objects.create(name=name, slug=slug)
    user = get_user_model().objects.create_user(username=username or f"{slug}_user", password="pw-12345678")
    Membership.objects.create(user=user, organization=org)
    return org, user


def make_call(org, investor_name, reference, amount, call_date=date(2026, 4, 1), funded="0"):
    investor, _ = Investor.objects.get_or_create(organization=org, name=investor_name)
    call = CapitalCall(
        organization=org, investor=investor, reference=reference, call_date=call_date,
        due_date=date(2026, 4, 30), amount_called=Decimal(amount), amount_funded=Decimal(funded),
    )
    call.refresh_status()
    call.save()
    return call


def seed_northwind():
    """Northwind data mirroring the demo seed, used against the sample statement."""
    org, user = make_org("Northwind Ventures", "northwind")
    calls = {
        "CC-1001": make_call(org, "Haller Capital LLC", "CC-1001", "20000.00"),
        "CC-1002": make_call(org, "Rahul Shah Trust", "CC-1002", "25000.00"),
        "CC-1003": make_call(org, "Patel Family Trust", "CC-1003", "25000.00"),
        "CC-1004": make_call(org, "Meridian Partners", "CC-1004", "15000.00"),
        "CC-1005": make_call(
            org, "Oakridge Holdings LLC", "CC-1005", "10000.00", call_date=date(2026, 1, 15), funded="10000.00"
        ),
        "CC-1006": make_call(org, "Oakridge Holdings LLC", "CC-1006", "15000.00"),
    }
    return org, user, calls


def seed_bluebird():
    org, user = make_org("Bluebird Capital", "bluebird")
    calls = {
        "CC-2001": make_call(org, "Cedar Grove Fund", "CC-2001", "40000.00"),
        "CC-2002": make_call(org, "Lakeshore Pension Plan", "CC-2002", "50000.00"),
    }
    return org, user, calls


def api_client_for(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client
