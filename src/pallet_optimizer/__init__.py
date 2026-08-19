"""AxioLoad transport loading optimizer."""

from fastapi import FastAPI

from .document_control_bootstrap import install_document_control_permissions, install_document_control_routes
from .facturx_bootstrap import install_facturx_permissions, install_facturx_routes

# Permissions must be extended before admin_service imports the catalog snapshots.
install_document_control_permissions()
install_facturx_permissions()

from .document_control_permissions import install_document_control_permission_migration

# Existing companies created before the document-control module need the new
# permission rows before AdminRepository resolves their effective rights.
install_document_control_permission_migration()

from . import prompt_center_system as _prompt_center_system
from .admin_coherence import install_admin_coherence
from .admin_panel import install_admin_panel_injection
from .auth_experience_panel import install_auth_experience_injection
from .circoe_workspace_v3 import install_circoe_workspace_v3
from .client_grouping import install_client_grouping
from .client_split_policy import install_client_split_policy
from .company_ai_dual_mode import install_company_ai_dual_mode
from .company_ai_endpoint import install_company_ai_endpoint
from .company_ai_privacy import install_company_ai_privacy
from .company_ai_user_surface import install_company_ai_user_surface
from .document_control_experience_panel import install_document_control_experience_injection
from .document_control_panel import install_document_control_panel_injection
from .document_control_system import install_document_control_system
from .facturx_panel import install_facturx_panel_injection
from .fixed_test_accounts import install_fixed_test_accounts
from .fixed_test_login_gate import install_fixed_test_login_gate
from .optimization_experience_panel import install_optimization_experience_injection
from .optimization_portfolio import install_optimization_portfolio
from .optimization_resilience import install_partial_model_success_policy
from .password_reset_panel import install_password_reset_injection
from .password_reset_system import install_password_reset_system
from .prompt_center_experience_panel import install_prompt_center_experience_injection
from .prompt_center_system import install_prompt_center_system
from .scaling import install_unlimited_item_count
from .security_hardening import install_security_hardening
from .security_upgrade import install_security_upgrade
from .super_admin_routes import install_super_admin_routes

__version__ = "0.20.0"

install_super_admin_routes()
install_password_reset_system()
install_fixed_test_accounts()
install_fixed_test_login_gate()
install_client_grouping()
install_optimization_portfolio()
install_partial_model_success_policy()
install_client_split_policy()
install_unlimited_item_count()
install_admin_panel_injection()
install_document_control_panel_injection()
install_document_control_experience_injection()
install_optimization_experience_injection()
install_facturx_panel_injection()
install_auth_experience_injection()
install_password_reset_injection()
install_prompt_center_experience_injection()
install_document_control_routes()
install_facturx_routes()
install_document_control_system()
_prompt_center_system._original_fastapi_init = FastAPI.__init__
install_prompt_center_system()
install_company_ai_endpoint()
install_company_ai_dual_mode()
install_company_ai_privacy()
install_company_ai_user_surface()
install_security_hardening()
# Install coherence after all FastAPI.__init__ wrappers so its admin route cannot
# be shadowed by a later compatibility installer.
install_admin_coherence()
# Install the visual shell last so it composes all existing business panels,
# including the Super Admin coherence surface, without replacing handlers,
# routes or optimization model/result rendering.
install_circoe_workspace_v3()
# Security is installed last so every route and compatibility layer is covered by
# the same fail-closed authentication, session and CSRF policy.
install_security_upgrade()
