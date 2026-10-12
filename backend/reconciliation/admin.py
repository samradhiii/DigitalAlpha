from django.contrib import admin

from .models import (
    BankTransaction,
    CapitalCall,
    ImportRowIssue,
    Investor,
    Membership,
    Organization,
    Payment,
    StatementImport,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "organization"]


@admin.register(Investor)
class InvestorAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "email"]
    list_filter = ["organization"]


@admin.register(CapitalCall)
class CapitalCallAdmin(admin.ModelAdmin):
    list_display = ["reference", "investor", "organization", "amount_called", "amount_funded", "status"]
    list_filter = ["organization", "status"]


@admin.register(StatementImport)
class StatementImportAdmin(admin.ModelAdmin):
    list_display = ["file_name", "organization", "uploaded_at", "total_rows", "imported_rows"]


@admin.register(ImportRowIssue)
class ImportRowIssueAdmin(admin.ModelAdmin):
    list_display = ["statement_import", "row_number", "issue_type"]


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ["transaction_date", "description", "amount", "status", "organization"]
    list_filter = ["organization", "status"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["capital_call", "amount", "approved_by", "approved_at"]
