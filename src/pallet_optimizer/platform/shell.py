from __future__ import annotations


def build_shell_capabilities(*, is_super_admin: bool) -> dict[str, bool]:
    """Return navigation capabilities without coupling the shell to business modules."""

    return {
        "show_settings": True,
        "show_management_center": is_super_admin,
    }
