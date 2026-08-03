from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "pallet_optimizer"


def test_post_pr23_runtime_layers_are_absent() -> None:
    forbidden_paths = (
        PACKAGE / "application_shell_panel.py",
        PACKAGE / "application_container.py",
        PACKAGE / "platform",
        PACKAGE / "static" / "application_shell.js",
        PACKAGE / "static" / "application_shell.css",
        PACKAGE / "static" / "history_stability.js",
        PACKAGE / "static" / "session_guard.js",
    )

    present = [str(path.relative_to(ROOT)) for path in forbidden_paths if path.exists()]
    assert not present, f"Couches postérieures à la PR 23 détectées : {present}"


def test_runtime_entrypoint_stays_on_pr23_composition() -> None:
    entrypoint = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    forbidden_markers = (
        "ApplicationContainer",
        "application_shell",
        "module_registry",
        "platform_modules",
        "history_stability",
    )

    found = [marker for marker in forbidden_markers if marker in entrypoint]
    assert not found, f"Composition postérieure à la PR 23 détectée : {found}"


def test_pr23_version_is_preserved() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_init = (PACKAGE / "__init__.py").read_text(encoding="utf-8")

    assert 'version = "0.19.2"' in pyproject
    assert '__version__ = "0.19.2"' in package_init
