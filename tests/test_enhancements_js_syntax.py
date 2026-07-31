from pathlib import Path


def test_enhancement_script_is_loaded_after_existing_applications():
    root = Path(__file__).resolve().parents[1]
    api = (root / "src" / "pallet_optimizer" / "api.py").read_text(encoding="utf-8")
    javascript = (root / "src" / "pallet_optimizer" / "static" / "enhancements.js").read_text(encoding="utf-8")
    assert "enhancements.js" in api
    assert "window.fetch" in javascript
    assert "drawFocusedRoute" in javascript


def test_enhancements_are_idempotent_and_do_not_poll_history_in_a_dom_loop():
    root = Path(__file__).resolve().parents[1]
    javascript = (root / "src" / "pallet_optimizer" / "static" / "enhancements.js").read_text(encoding="utf-8")

    assert "axioload:history-loaded" in javascript
    assert "runtime.historyRequest" in javascript
    assert "node.nodeType === Node.ELEMENT_NODE" in javascript
    assert "if (title && title.textContent !== nextTitle)" in javascript
    assert "if (badge.textContent !== nextText)" in javascript
    assert "refreshHistory();window.AxioEnhancements" not in javascript


def test_history_transport_requires_a_concrete_refresh_permission():
    root = Path(__file__).resolve().parents[1]
    guard = (root / "src" / "pallet_optimizer" / "static" / "history_stability.js").read_text(encoding="utf-8")

    assert "refreshPermit = 1" in guard
    assert "grantRefresh('user-action')" in guard
    assert "if (cachedResponse && !explicitlyAllowed)" in guard
    assert "MAX_NETWORK_REQUESTS = 3" in guard
    assert "NETWORK_WINDOW_MS = 30 * 1000" in guard
    assert "mutatesHistory && response.ok" in guard
