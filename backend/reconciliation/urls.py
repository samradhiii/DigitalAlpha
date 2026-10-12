from django.urls import path

from . import views

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("investors/", views.InvestorListView.as_view(), name="investor-list"),
    path("capital-calls/", views.CapitalCallListView.as_view(), name="capital-call-list"),
    path("imports/", views.StatementImportListCreateView.as_view(), name="import-list"),
    path("imports/<int:pk>/", views.StatementImportDetailView.as_view(), name="import-detail"),
    path("transactions/", views.TransactionListView.as_view(), name="transaction-list"),
    path("transactions/<int:pk>/", views.TransactionDetailView.as_view(), name="transaction-detail"),
    path(
        "transactions/<int:pk>/approve/",
        views.TransactionActionView.as_view(action="approve"),
        name="transaction-approve",
    ),
    path(
        "transactions/<int:pk>/reject/",
        views.TransactionActionView.as_view(action="reject"),
        name="transaction-reject",
    ),
    path(
        "transactions/<int:pk>/ignore/",
        views.TransactionActionView.as_view(action="ignore"),
        name="transaction-ignore",
    ),
]
