"""AxioLoad transport loading optimizer."""

from .document_control_bootstrap import install_document_control_permissions, install_document_control_routes

# Permissions must be extended before admin_service imports the catalog snapshots.
install_document_control_permissions()

from .document_control_permissions import install_document_control_permission_migration

# Existing companies created before the document-control module need the new
# permission rows before AdminRepository resolves their effective rights.
install_document_control_permission_migration()

from .admin_panel import install_admin_panel_injection
from .client_grouping import install_client_grouping
from .client_split_policy import install_client_split_policy
from .document_control_experience_panel import install_document_control_experience_injection
from .document_control_panel import install_document_control_panel_injection
from .document_control_system import install_document_control_system
from .optimization_experience_panel import install_optimization_experience_injection
from .optimization_portfolio import install_optimization_portfolio
from .scaling import install_unlimited_item_count

__version__ = "0.15.0"

install_client_grouping()
install_optimization_portfolio()
install_client_split_policy()
install_unlimited_item_count()
install_admin_panel_injection()
install_document_control_panel_injection()
install_document_control_experience_injection()
install_optimization_experience_injection()
install_document_control_routes()
install_document_control_system()
