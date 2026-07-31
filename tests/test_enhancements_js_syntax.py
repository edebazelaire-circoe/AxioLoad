from pathlib import Path


def test_enhancement_script_is_loaded_after_existing_applications():
    root = Path(__file__).resolve().parents[1]
    api = (root / "src" / "pallet_optimizer" / "api.py").read_text(encoding="utf-8")
    javascript = (root / "src" / "pallet_optimizer" / "static" / "enhancements.js").read_text(encoding="utf-8")
    assert "enhancements.js" in api
    assert "window.fetch" in javascript
    assert "drawFocusedRoute" in javascript


def test_history_refresh_is_explicit_and_never_controls_unrelated_requests():
    root = Path(__file__).resolve().parents[1]
    javascript = (root / "src" / "pallet_optimizer" / "static" / "enhancements.js").read_text(encoding="utf-8")

    assert "runtime.historyRequest" in javascript
    assert "nativeFetch('/api/history?limit=200'" in javascript
    assert "axioload:history-refresh-request" in javascript
    assert "refreshHistory(true, 'validation')" in javascript
    assert "cachedResponse" not in javascript
    assert "refreshPermit" not in javascript
    assert "circuitIsOpen" not in javascript


def test_dom_observers_are_limited_to_feature_containers():
    root = Path(__file__).resolve().parents[1]
    javascript = (root / "src" / "pallet_optimizer" / "static" / "enhancements.js").read_text(encoding="utf-8")

    assert "observer.observe(document.body" not in javascript
    assert "observeContainer('#vehicle-table tbody'" in javascript
    assert "observeContainer('#cargo-table tbody'" in javascript
    assert "observeContainer('#history-list'" in javascript
    assert "root.dataset.axioloadObserved" in javascript
