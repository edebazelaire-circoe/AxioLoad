from __future__ import annotations

import os

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

    def super_admin_actor(self, provided_token: str | None = None) -> str:
        """Return the configured Super Admin identity without an extra token prompt.

        The current application is operated as a simple local administration workspace.
        A real identity provider can replace this method when client authentication is
        connected, without changing the administration screens.
        """
        del provided_token
        return os.getenv("PLO_SUPER_ADMIN_EMAIL", "superadmin@axioload.local").strip() or "superadmin@axioload.local"
