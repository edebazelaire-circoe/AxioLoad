from pathlib import Path


def test_enhancement_script_is_loaded_after_existing_applications():
    root = Path(__file__).resolve().parents[1]
    api = (root / "src" / "pallet_optimizer" / "api.py").read_text(encoding="utf-8")
    javascript = (root / "src" / "pallet_optimizer" / "static" / "enhancements.js").read_text(encoding="utf-8")
    assert "enhancements.js" in api
    assert "window.fetch" in javascript
    assert "drawFocusedRoute" in javascript
