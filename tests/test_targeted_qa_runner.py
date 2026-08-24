from pathlib import Path

import pytest

from pallet_optimizer.qa_targeted_runner import (
    MAX_REPETITIONS,
    ROOT,
    SCENARIOS,
    _extract_repetitions,
    _extract_scenario,
)


def test_targeted_qa_runner_parses_single_issue_contract():
    title = "[QA RUN] CIBLE AXIO-OPT-SMALL-001"
    body = "Mode: CIBLE\nScenario: AXIO-OPT-SMALL-001\nRequested ref: main\nRepetitions: 5\n"
    assert _extract_scenario(title, body) == "AXIO-OPT-SMALL-001"
    assert _extract_repetitions(body) == 5


def test_targeted_qa_runner_defaults_to_one_repetition_and_can_read_body_scenario():
    body = "Mode: CIBLE\nScenario: AXIO-VEHICLE-CRUD-001\nRequested ref: main\n"
    assert _extract_scenario("[QA RUN] CIBLE", body) == "AXIO-VEHICLE-CRUD-001"
    assert _extract_repetitions(body) == 1


def test_targeted_qa_runner_rejects_unbounded_repetition_count():
    with pytest.raises(ValueError):
        _extract_repetitions(f"Repetitions: {MAX_REPETITIONS + 1}\n")


def test_every_whitelisted_targeted_scenario_points_to_a_real_test_file():
    assert SCENARIOS
    for scenario_id, scenario in SCENARIOS.items():
        path = ROOT / scenario.test_path
        assert path.is_file(), f"{scenario_id} points to missing test file: {Path(scenario.test_path)}"
