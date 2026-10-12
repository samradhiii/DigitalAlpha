from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .csv_parser import CSVFileError
from .models import BankTransaction, CapitalCall, Investor, StatementImport
from .permissions import HasOrganization, get_user_organization
from .serializers import (
    BankTransactionSerializer,
    CapitalCallSerializer,
    InvestorSerializer,
    LoginSerializer,
    ReviewActionSerializer,
    StatementImportDetailSerializer,
    StatementImportSerializer,
    UploadSerializer,
)


def _me_payload(user, token=None):
    org = get_user_organization(user)
    payload = {
        "username": user.username,
        "organization": {"id": org.id, "name": org.name, "slug": org.slug} if org else None,
    }
    if token:
        payload["token"] = token.key
    return payload


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
        if get_user_organization(user) is None:
            return Response(
                {"detail": "Your account is not linked to an organization."}, status=status.HTTP_403_FORBIDDEN
            )
        token, _ = Token.objects.get_or_create(user=user)
        return Response(_me_payload(user, token))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [HasOrganization]

    def get(self, request):
        return Response(_me_payload(request.user))


class OrganizationScopedMixin:
    """Every queryset is filtered to the requesting user's organization.

    Objects belonging to another organization are simply not found (404), so
    their existence is never revealed.
    """

    permission_classes = [HasOrganization]

    @property
    def organization(self):
        return get_user_organization(self.request.user)


class InvestorListView(OrganizationScopedMixin, generics.ListAPIView):
    serializer_class = InvestorSerializer

    def get_queryset(self):
        zero = Value(0, output_field=DecimalField(max_digits=16, decimal_places=2))
        return (
            Investor.objects.filter(organization=self.organization)
            .annotate(
                total_called=Coalesce(Sum("capital_calls__amount_called"), zero),
                total_funded=Coalesce(Sum("capital_calls__amount_funded"), zero),
            )
            .annotate(remaining_balance=F("total_called") - F("total_funded"))
        )


class CapitalCallListView(OrganizationScopedMixin, generics.ListAPIView):
    serializer_class = CapitalCallSerializer

    def get_queryset(self):
        qs = CapitalCall.objects.filter(organization=self.organization).select_related("investor")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        return qs


class StatementImportListCreateView(OrganizationScopedMixin, generics.ListAPIView):
    serializer_class = StatementImportSerializer

    def get_queryset(self):
        return StatementImport.objects.filter(organization=self.organization).select_related("uploaded_by")

    def post(self, request):
        serializer = UploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        if not upload.name.lower().endswith(".csv"):
            return Response({"detail": "Please upload a .csv file."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > settings.MAX_CSV_UPLOAD_BYTES:
            return Response({"detail": "File is too large (maximum 5 MB)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            statement = services.import_statement(
                organization=self.organization, user=request.user, file_name=upload.name, content=upload.read()
            )
        except CSVFileError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StatementImportDetailSerializer(statement).data, status=status.HTTP_201_CREATED)


class StatementImportDetailView(OrganizationScopedMixin, generics.RetrieveAPIView):
    serializer_class = StatementImportDetailSerializer

    def get_queryset(self):
        return StatementImport.objects.filter(organization=self.organization).prefetch_related(
            "issues", "transactions__suggested_investor", "transactions__suggested_capital_call"
        )


class TransactionListView(OrganizationScopedMixin, generics.ListAPIView):
    serializer_class = BankTransactionSerializer

    def get_queryset(self):
        qs = BankTransaction.objects.filter(organization=self.organization).select_related(
            "suggested_investor", "suggested_capital_call", "reviewed_by"
        )
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"].upper())
        if params.get("import", "").isdigit():
            qs = qs.filter(statement_import_id=int(params["import"]))
        return qs


class TransactionDetailView(OrganizationScopedMixin, generics.RetrieveAPIView):
    serializer_class = BankTransactionSerializer

    def get_queryset(self):
        return BankTransaction.objects.filter(organization=self.organization)


class TransactionActionView(OrganizationScopedMixin, APIView):
    action = None  # "approve" | "reject" | "ignore"

    def post(self, request, pk):
        # Resolve within the organization first so IDs from other organizations return 404.
        get_object_or_404(BankTransaction, pk=pk, organization=self.organization)
        serializer = ReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        kwargs = {"organization": self.organization, "user": request.user, "transaction_id": pk, "note": data["note"]}
        try:
            if self.action == "approve":
                tx = services.approve_transaction(capital_call_id=data.get("capital_call_id"), **kwargs)
            elif self.action == "reject":
                tx = services.reject_transaction(**kwargs)
            else:
                tx = services.ignore_transaction(**kwargs)
        except services.ReconciliationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        tx = BankTransaction.objects.select_related(
            "suggested_investor", "suggested_capital_call", "reviewed_by"
        ).get(pk=tx.pk)
        return Response(BankTransactionSerializer(tx).data)
