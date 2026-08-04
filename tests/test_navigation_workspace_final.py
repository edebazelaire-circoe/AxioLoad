from pathlib import Path


def test_workspace_internal_clicks_are_allowed() -> None:
    root = Path(__file__).parents[1] / 'src/pallet_optimizer/static'
    guard = (root / 'navigation_guard.js').read_text(encoding='utf-8')
    workspace = (root / 'document_control_experience_v2.js').read_text(encoding='utf-8')
    assert 'if (!event.isTrusted) return' in guard
    assert 'target.click()' in workspace
    assert 'documentTab.click()' in workspace
