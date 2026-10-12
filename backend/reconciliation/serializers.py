from rest_framework import serializers

from .models import BankTransaction, CapitalCall, ImportRowIssue, Investor, StatementImport


class InvestorSerializer(serializers.ModelSerializer):
    total_called = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    total_funded = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    remaining_balance = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    payment_status = serializers.SerializerMethodField()

    class Meta:
        model = Investor
        fields = ["id", "name", "email", "total_called", "total_funded", "remaining_balance", "payment_status"]

    def get_payment_status(self, investor):
        if investor.total_funded <= 0:
            return CapitalCall.Status.PENDING
        if investor.remaining_balance > 0:
            return CapitalCall.Status.PARTIALLY_FUNDED
        return CapitalCall.Status.FUNDED


class CapitalCallSerializer(serializers.ModelSerializer):
    investor_name = serializers.CharField(source="investor.name", read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = CapitalCall
        fields = [
            "id", "reference", "investor", "investor_name", "call_date", "due_date",
            "amount_called", "amount_funded", "remaining_amount", "status",
        ]


class BankTransactionSerializer(serializers.ModelSerializer):
    suggested_investor_name = serializers.CharField(source="suggested_investor.name", default=None, read_only=True)
    suggested_capital_call_reference = serializers.CharField(
        source="suggested_capital_call.reference", default=None, read_only=True
    )
    reviewed_by = serializers.CharField(source="reviewed_by.username", default=None, read_only=True)

    class Meta:
        model = BankTransaction
        fields = [
            "id", "statement_import", "row_number", "transaction_date", "description", "amount",
            "transaction_type", "bank_reference", "status", "confidence",
            "suggested_investor", "suggested_investor_name",
            "suggested_capital_call", "suggested_capital_call_reference",
            "match_reasons", "review_reasons", "reviewed_by", "reviewed_at", "review_note",
        ]


class ImportRowIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRowIssue
        fields = ["row_number", "issue_type", "messages", "raw_data"]


class StatementImportSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.CharField(source="uploaded_by.username", default=None, read_only=True)

    class Meta:
        model = StatementImport
        fields = [
            "id", "file_name", "uploaded_at", "uploaded_by", "total_rows", "imported_rows", "invalid_rows",
            "duplicate_rows", "suggested_matches", "needs_review", "ignored_rows",
        ]


class StatementImportDetailSerializer(StatementImportSerializer):
    issues = ImportRowIssueSerializer(many=True, read_only=True)
    transactions = BankTransactionSerializer(many=True, read_only=True)

    class Meta(StatementImportSerializer.Meta):
        fields = StatementImportSerializer.Meta.fields + ["issues", "transactions"]


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class ReviewActionSerializer(serializers.Serializer):
    capital_call_id = serializers.IntegerField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)
