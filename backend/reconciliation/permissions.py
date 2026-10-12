from rest_framework.permissions import BasePermission

from .models import Membership


def get_user_organization(user):
    try:
        return user.membership.organization
    except Membership.DoesNotExist:
        return None


class HasOrganization(BasePermission):
    """Authenticated user who belongs to an organization."""

    message = "Your account is not linked to an organization."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and get_user_organization(request.user))
