from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "pallet_optimizer" / "static"


def test_superadmin_settings_remain_visible_and_clickable() -> None:
    script = (STATIC / "auth_experience.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "auth_experience.css").read_text(encoding="utf-8")

    assert "document.body.dataset.superAdminShell" in script
    assert "settingsButton.classList.remove('hidden')" in script
    assert "settingsButton.disabled = false" in script
    assert 'body[data-super-admin-shell="true"] #open-settings{display:inline-flex!important}' in stylesheet


def test_standard_user_management_button_stays_hidden() -> None:
    script = (STATIC / "auth_experience.js").read_text(encoding="utf-8")
    stylesheet = (STATIC / "auth_experience.css").read_text(encoding="utf-8")

    assert "document.body.dataset.userShell" in script
    assert "adminButton.classList.add('hidden')" in script
    assert 'body[data-user-shell="true"] #open-admin{display:none!important}' in stylesheet


def test_requested_interface_copy_is_applied_without_dom_observer() -> None:
    script = (STATIC / "auth_experience.js").read_text(encoding="utf-8")

    assert "vehicleButton.textContent = 'Véhicules'" in script
    assert "Cet espace permet de consulter les règles utilisées par l’IA" in script
    assert "MutationObserver" not in script
