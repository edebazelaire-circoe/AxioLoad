from pathlib import Path


SCRIPT = Path("src/pallet_optimizer/static/auth_experience.js")


def test_superadmin_settings_button_is_forced_visible() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    assert "if (directAdmin && settingsButton)" in content
    assert "settingsButton.hidden = false" in content
    assert "settingsButton.disabled = false" in content


def test_standard_user_admin_button_is_hidden() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    assert "if (authenticatedUser && !directAdmin && !assistance && adminButton)" in content
    assert "adminButton.hidden = true" in content
    assert "adminButton.disabled = true" in content


def test_no_global_dom_observer_is_added() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    assert "MutationObserver" not in content
    assert "observe(document.body" not in content
