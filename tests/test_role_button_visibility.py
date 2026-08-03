from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTH_SCRIPT = ROOT / "src" / "pallet_optimizer" / "static" / "auth_experience.js"
AUTH_PANEL = ROOT / "src" / "pallet_optimizer" / "auth_experience_panel.py"


def test_role_buttons_are_explicitly_controlled() -> None:
    script = AUTH_SCRIPT.read_text(encoding="utf-8")

    assert "function applyRoleButtonVisibility" in script
    assert "if (directAdmin && settingsButton)" in script
    assert "settingsButton.hidden = false" in script
    assert "settingsButton.disabled = false" in script
    assert "if (authenticatedUser && !directAdmin && !assistance && adminButton)" in script
    assert "adminButton.hidden = true" in script
    assert "adminButton.disabled = true" in script
    assert "new MutationObserver" not in script


def test_role_button_fix_uses_versioned_existing_asset() -> None:
    panel = AUTH_PANEL.read_text(encoding="utf-8")

    assert 'auth_experience.js?v=0.19.2' in panel
    assert 'auth_experience.css?v=0.19.2' in panel
