from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAX_REPETITIONS = 10


@dataclass(frozen=True)
class Scenario:
    test_path: str
    oracle: str


SCENARIOS: dict[str, Scenario] = {
    "AXIO-OPT-SMALL-001": Scenario(
        test_path="tests/test_qa_axioload_exact_small_001.py",
        oracle=(
            "5 palettes 1200x1200 mm, exactly 2 vehicles, total occupied length 3.6 m, "
            "5 unique placements, no overlap, no dimension/weight error diagnostic."
        ),
    ),
    "AXIOLOAD-AI-DOCUMENT-001": Scenario(
        test_path="tests/test_qa_axioload_ai_document_001.py",
        oracle=(
            "Document-control analysis reproduces only supported fixture facts, visible UI values match "
            "the structured analysis, and the persisted result is identical after reload."
        ),
    ),
    "AXIO-VEHICLE-CRUD-001": Scenario(
        test_path="tests/test_qa_axioload_vehicle_crud_001.py",
        oracle=(
            "Synthetic vehicle creation, reload, versioned modification, persisted dimensions/capacity, "
            "and cleanup all succeed in isolated QA storage."
        ),
    ),
    "AXIO-IMPORT-OPT-EXPORT-001": Scenario(
        test_path="tests/test_qa_axioload_import_opt_export_001.py",
        oracle=(
            "Synthetic XLSX import expands 5 items, optimization returns 5 unique placements, history "
            "persists, exported XLSX matches placements, and the QA run is deleted."
        ),
    ),
    "AXIO-CONSTRAINT-STRESS-001": Scenario(
        test_path="tests/test_qa_axioload_constraint_stress_001.py",
        oracle=(
            "Exact physical limits are accepted and +1 boundary violations, payload, axle, LIFO and "
            "incompatibility cases produce the expected deterministic diagnostics."
        ),
    ),
    "AXIO-MULTI-SIM-001": Scenario(
        test_path="tests/test_qa_axioload_multi_sim_ui_001.py",
        oracle=(
            "Five distinct deterministic simulations are executed through the real AxioLoad browser UI: "
            "8/15/24/36/50 pallets for 1/2/3/4/5 clients. Every case must place every pallet, expose every "
            "client in the result UI, return no geometry overlap or error diagnostic, clean its QA history, "
            "and capture both input and result screenshots. Vehicle counts and occupied lengths are observed "
            "business outputs, not hard-coded optimum claims."
        ),
    ),
}


def _extract_scenario(title: str, body: str) -> str | None:
    prefix = "[QA RUN] CIBLE "
    if title.startswith(prefix):
        candidate = title[len(prefix) :].strip()
        if candidate:
            return candidate
    match = re.search(r"(?im)^Scenario\s*:\s*([A-Z0-9-]+)\s*$", body)
    return match.group(1) if match else None


def _extract_repetitions(body: str) -> int:
    match = re.search(r"(?im)^Repetitions?\s*:\s*(\d+)\s*$", body)
    if not match:
        return 1
    repetitions = int(match.group(1))
    if repetitions < 1 or repetitions > MAX_REPETITIONS:
        raise ValueError(f"Repetitions must be between 1 and {MAX_REPETITIONS}")
    return repetitions


def _junit_counts(path: Path) -> dict[str, int | float]:
    if not path.exists():
        return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time_s": 0.0}
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        "tests": sum(int(suite.attrib.get("tests", 0)) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", 0)) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", 0)) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", 0)) for suite in suites),
        "time_s": round(sum(float(suite.attrib.get("time", 0.0)) for suite in suites), 3),
    }


def _read_evidence(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _format_evidence(evidence: dict[str, object]) -> str:
    if not evidence:
        return "no scenario-specific metric file emitted; pytest assertions are the available proof"

    simulations = evidence.get("simulations")
    if isinstance(simulations, list) and simulations:
        header = (
            f"execution_layer={evidence.get('execution_layer')}, simulation_count={evidence.get('simulation_count')}, "
            f"all_cases_distinct={evidence.get('all_cases_distinct')}, total_pallets_tested={evidence.get('total_pallets_tested')}, "
            f"total_clients_tested={evidence.get('total_clients_tested')}, screenshot_count={evidence.get('screenshot_count')}, "
            f"report_file={evidence.get('report_file')}"
        )
        details = []
        for simulation in simulations:
            if not isinstance(simulation, dict):
                continue
            details.append(
                "    - "
                f"{simulation.get('case_id')}: pallets={simulation.get('pallet_count')}, "
                f"clients={simulation.get('client_count')}, vehicles={simulation.get('vehicle_count')}, "
                f"occupied_length_m={simulation.get('occupied_length_m')}, placements={simulation.get('placement_count')}, "
                f"overlaps={simulation.get('geometry_overlap_count')}, errors={simulation.get('error_diagnostic_count')}, "
                f"input_capture={simulation.get('input_screenshot')}, result_capture={simulation.get('result_screenshot')}"
            )
        return header + "\n" + "\n".join(details)

    preferred = [
        "execution_layer",
        "optimizer_status",
        "vehicle_count",
        "occupied_length_m",
        "placement_count",
        "unique_placement_count",
        "geometry_overlap_count",
        "dimension_violation_count",
        "weight_violation_count",
        "error_diagnostic_count",
        "browser_exercised",
        "server_exercised",
    ]
    parts = [f"{key}={evidence[key]}" for key in preferred if key in evidence]
    return ", ".join(parts) if parts else json.dumps(evidence, ensure_ascii=False, sort_keys=True)


def _write_summary(
    output_dir: Path,
    *,
    scenario_id: str | None,
    scenario: Scenario | None,
    repetitions: int,
    runs: list[dict[str, object]],
    conclusion: str,
    reason: str | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for run in runs if run.get("passed") is True)
    failed = sum(1 for run in runs if run.get("passed") is False)
    sha = os.environ.get("GITHUB_SHA", "unknown")
    ref = os.environ.get("GITHUB_REF_NAME", "main") or "main"
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repository = os.environ.get("GITHUB_REPOSITORY", "edebazelaire-circoe/AxioLoad")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = f"{server}/{repository}/actions/runs/{run_id}" if run_id else "unavailable"

    summary = {
        "conclusion": conclusion,
        "scenario_id": scenario_id,
        "test_path": scenario.test_path if scenario else None,
        "oracle": scenario.oracle if scenario else None,
        "requested_repetitions": repetitions,
        "executed_repetitions": len(runs),
        "passed_repetitions": passed,
        "failed_repetitions": failed,
        "ref": ref,
        "sha": sha,
        "run_url": run_url,
        "reason": reason,
        "runs": runs,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "## QA targeted evidence",
        f"- Conclusion technique : **{conclusion}**",
        f"- Scénario : `{scenario_id or 'UNKNOWN'}`",
        f"- Branche/ref : `{ref}`",
        f"- Commit testé : `{sha}`",
        f"- GitHub Actions : {run_url}",
    ]
    if scenario:
        lines.extend(
            [
                f"- Test exécuté : `{scenario.test_path}`",
                f"- Commande : `python -m pytest -q -s {scenario.test_path} --junitxml=<report>`",
                f"- Répétitions : **{passed}/{repetitions} PASS** ({failed} échec(s))",
                "",
                "### Oracle attendu",
                scenario.oracle,
                "",
                "### Preuves par répétition",
            ]
        )
        for run in runs:
            counts = run.get("junit", {})
            status = "PASS" if run.get("passed") else "FAIL"
            lines.append(
                f"- {run['index']}/{repetitions} — **{status}** — "
                f"tests={counts.get('tests', 0)}, failures={counts.get('failures', 0)}, "
                f"errors={counts.get('errors', 0)}, skipped={counts.get('skipped', 0)}, "
                f"time={counts.get('time_s', 0.0)}s"
            )
            formatted = _format_evidence(run.get("evidence", {}))
            lines.append("  - " + formatted.replace("\n", "\n"))
    if reason:
        lines.extend(["", "### Motif", reason])
    lines.extend(
        [
            "",
            "Le statut ci-dessus provient de l'exécution du fichier de test indiqué sur le commit indiqué ; "
            "il ne doit pas être reformulé comme une simple réussite de CI générique.",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(title: str, body: str, output_dir: Path) -> int:
    scenario_id = _extract_scenario(title, body)
    try:
        repetitions = _extract_repetitions(body)
    except ValueError as exc:
        _write_summary(
            output_dir,
            scenario_id=scenario_id,
            scenario=None,
            repetitions=0,
            runs=[],
            conclusion="BLOCKED",
            reason=str(exc),
        )
        return 2

    scenario = SCENARIOS.get(scenario_id or "")
    if scenario is None:
        _write_summary(
            output_dir,
            scenario_id=scenario_id,
            scenario=None,
            repetitions=repetitions,
            runs=[],
            conclusion="BLOCKED",
            reason="Scenario is not present in the AxioLoad targeted-test whitelist.",
        )
        return 2

    test_path = ROOT / scenario.test_path
    if not test_path.exists():
        _write_summary(
            output_dir,
            scenario_id=scenario_id,
            scenario=scenario,
            repetitions=repetitions,
            runs=[],
            conclusion="BLOCKED",
            reason=f"Mapped test file is missing: {scenario.test_path}",
        )
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, object]] = []
    for index in range(1, repetitions + 1):
        junit_path = output_dir / f"junit-{index}.xml"
        evidence_path = output_dir / f"evidence-{index}.json"
        log_path = output_dir / f"pytest-{index}.log"
        env = os.environ.copy()
        env["QA_EVIDENCE_PATH"] = str(evidence_path)
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-s",
            scenario.test_path,
            f"--junitxml={junit_path}",
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        combined_log = completed.stdout + ("\n" + completed.stderr if completed.stderr else "")
        log_path.write_text(combined_log, encoding="utf-8")
        print(f"===== {scenario_id} repetition {index}/{repetitions} =====")
        print(combined_log)
        runs.append(
            {
                "index": index,
                "passed": completed.returncode == 0,
                "exit_code": completed.returncode,
                "junit": _junit_counts(junit_path),
                "evidence": _read_evidence(evidence_path),
                "log_file": log_path.name,
                "junit_file": junit_path.name,
            }
        )

    conclusion = "SUCCESS" if all(run["passed"] for run in runs) else "FAILURE"
    _write_summary(
        output_dir,
        scenario_id=scenario_id,
        scenario=scenario,
        repetitions=repetitions,
        runs=runs,
        conclusion=conclusion,
    )
    return 0 if conclusion == "SUCCESS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="qa-results")
    args = parser.parse_args()
    title = os.environ.get("QA_REQUEST_TITLE", "")
    body = os.environ.get("QA_REQUEST_BODY", "")
    return run(title, body, Path(args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
