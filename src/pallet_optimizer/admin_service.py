from __future__ import annotations

from .admin_base import (
    DEFAULT_NEW_COMPANY_PERMISSIONS, PERMISSION_CATALOG, PERMISSION_KEYS, WebContext,
)
from .admin_invitations import AdminInvitationsMixin
from .admin_integrations import AdminIntegrationsMixin
from .admin_permissions import AdminPermissionsMixin
from .admin_reporting import AdminReportingMixin
from .admin_base import AdminBaseMixin


class AdminRepository(
    AdminInvitationsMixin, AdminPermissionsMixin, AdminIntegrationsMixin,
    AdminReportingMixin, AdminBaseMixin,
):
    """Transitional SQLite-backed administration boundary."""

