"""AxioLoad transport loading optimizer."""

from .document_control_bootstrap import install_document_control_permissions, install_document_control_routes

# Permissions must be extended before admin_service imports the catalog snapshots.
install_document_control_permissions()

from .document_control_permissions import install_document_control_permission_migration

# Existing companies created before the document-control module need the new
# permission rows before AdminRepository resolves their effective rights.
install_document_control_permission_migration()

from .admin_panel import install_admin_panel_injection
from .document_control_panel import install_document_control_panel_injection
from .scaling import install_unlimited_item_count

__version__ = "0.13.0"

install_unlimited_item_count()
install_admin_panel_injection()
install_document_control_panel_injection()
install_document_control_routes()
