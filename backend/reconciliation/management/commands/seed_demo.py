from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from reconciliation.models import (
    BankTransaction,
    CapitalCall,
    Investor,
    Membership,
    Organization,
    Payment,
    StatementImport,
)

DEMO_PASSWORD = "demo12345"

# (reference, investor, call_date, due_date, amount_called, amount_already_funded)
DEMO_DATA = {
    ("Northwind Ventures", "northwind", "northwind_admin"): [
        ("CC-1001", "Haller Capital LLC", date(2026, 4, 1), date(2026, 4, 30), "20000.00", "0"),
        ("CC-1002", "Rahul Shah Trust", date(2026, 4, 1), date(2026, 4, 30), "25000.00", "0"),
        ("CC-1003", "Patel Family Trust", date(2026, 4, 1), date(2026, 4, 30), "25000.00", "0"),
        ("CC-1004", "Meridian Partners", date(2026, 4, 1), date(2026, 4, 30), "15000.00", "0"),
        # An earlier call that was already settled before this system existed.
        ("CC-1005", "Oakridge Holdings LLC", date(2026, 1, 15), date(2026, 2, 15), "10000.00", "10000.00"),
        ("CC-1006", "Oakridge Holdings LLC", date(2026, 4, 1), date(2026, 4, 30), "15000.00", "0"),
    ],
    ("Bluebird Capital", "bluebird", "bluebird_admin"): [
        ("CC-2001", "Cedar Grove Fund", date(2026, 4, 1), date(2026, 4, 30), "40000.00", "0"),
        ("CC-2002", "Lakeshore Pension Plan", date(2026, 4, 1), date(2026, 4, 30), "50000.00", "0"),
        ("CC-2003", "Meridian Partners", date(2026, 4, 1), date(2026, 4, 30), "30000.00", "0"),
    ],
}


class Command(BaseCommand):
    help = "Create the demo organizations, users, investors and capital calls (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all imports, transactions and payments for the demo organizations and reset balances.",
        )

    @transaction.atomic
    def handle(self, *args, reset=False, **options):
        User = get_user_model()
        for (org_name, slug, username), calls in DEMO_DATA.items():
            org, _ = Organization.objects.get_or_create(slug=slug, defaults={"name": org_name})

            if reset:
                Payment.objects.filter(organization=org).delete()
                BankTransaction.objects.filter(organization=org).delete()
                StatementImport.objects.filter(organization=org).delete()

            user, created = User.objects.get_or_create(username=username)
            if created or reset:
                user.set_password(DEMO_PASSWORD)
                user.save()
            Membership.objects.update_or_create(user=user, defaults={"organization": org})

            for reference, investor_name, call_date, due_date, called, funded in calls:
                investor, _ = Investor.objects.get_or_create(
                    organization=org,
                    name=investor_name,
                    defaults={"email": f"ops@{investor_name.lower().replace(' ', '')}.example"},
                )
                call, created = CapitalCall.objects.get_or_create(
                    organization=org,
                    reference=reference,
                    defaults={
                        "investor": investor, "call_date": call_date, "due_date": due_date,
                        "amount_called": Decimal(called),
                    },
                )
                if created or reset:
                    call.amount_funded = Decimal(funded)
                    call.refresh_status()
                    call.save()

            self.stdout.write(f"{org_name}: login '{username}' / '{DEMO_PASSWORD}', {len(calls)} capital calls")

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
