#!/usr/bin/env python3
"""Bounded assertion runner with fresh, structured pytest verdict evidence."""
# evorthon-implements: EVD-README-026
# evorthon-implements: EVD-README-035
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERDICTS = ROOT / "artifacts" / "verdicts"
BUDGETS = {"fast": 240, "deep": 900}
# How long one wait for the child lasts before the wrapper reports that it is still running.
HEARTBEAT_SECONDS = 15
# The one test that carries the deliberate assertion the injected-assertion
# switch turns on. Nothing else reads that switch.
SENTINEL_TEST = "tests/test_sentinel.py"
LOG_TAIL_MAX_CHARS = 4096
PYTEST_TIMEOUT_BANNER = re.compile(r"^\+{3,}\s+Timeout\s+\+{3,}\s*$", re.MULTILINE)
PYTEST_TIMEOUT_STACK = re.compile(r"^~{3,}\s+Stack of .+ \(\d+\)\s+~{3,}\s*$", re.MULTILINE)


def executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(f"required executable is unavailable: {name}")
    path = pathlib.Path(found).resolve()
    if os.name == "nt" and path.suffix.lower() != ".exe":
        raise RuntimeError(f"Windows executable must resolve to .exe: {path}")
    return str(path)


def pytest_timeout_contract() -> tuple[int, str]:
    """Read the one pytest timeout declaration that pytest enforces."""
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    options = configuration["tool"]["pytest"]["ini_options"]
    seconds = int(options["timeout"])
    method = str(options["timeout_method"])
    if seconds <= 0 or method != "thread":
        raise ValueError("pytest timeout must be a positive Windows thread timeout")
    return seconds, method


def marker_filter_for(lane: str, scoped: bool) -> str:
    """Decide the one pytest -m override for this invocation.

    Only the whole, unscoped fast lane deselects deep-marked tests. A whole deep
    lane and any scoped invocation (positional test paths given) run with no
    marker filter, overriding pyproject.toml's own -m "not deep" addopts.
    """
    if lane == "deep" or scoped:
        return ""
    return "not deep"


def wall_budget(lane: str, scoped: bool) -> int:
    """Decide the one wall deadline for this invocation.

    A scoped invocation always takes the deep budget, whatever --lane names,
    because a positionally selected deep-marked test can run as long as the
    deep lane allows.
    """
    return BUDGETS["deep"] if scoped else BUDGETS[lane]


def selection_covers_sentinel(tests: list[str]) -> bool:
    """Say whether a positional selection already reaches the sentinel test."""
    sentinel = pathlib.PurePosixPath(SENTINEL_TEST)
    for entry in tests:
        target = pathlib.PurePath(entry.split("::")[0]).as_posix().strip("/")
        if not target or target == ".":
            return True
        selected = pathlib.PurePosixPath(target)
        if selected == sentinel or sentinel.is_relative_to(selected):
            return True
    return False


def injected_selection(tests: list[str], inject_assertion: bool) -> list[str]:
    """Decide the positional selection an injected-assertion run actually gives pytest.

    The deliberate assertion lives in one sentinel test, so a positional
    selection that leaves the sentinel out injects nothing while still naming a
    verdict file for the red path. Of the two honest answers, refusing the
    combination or running the sentinel beside the selection, this runner takes
    the second: the sentinel is added to the selection, so the red path a
    scoped seen-RED run claims is a red path that really ran. A selection that
    already reaches the sentinel is passed through unchanged.
    """
    if not inject_assertion or not tests or selection_covers_sentinel(tests):
        return list(tests)
    return [*tests, SENTINEL_TEST]


def verdict_file_name(lane: str, scoped: bool, inject_assertion: bool) -> str:
    """Name the one verdict file this invocation writes.

    A scoped invocation never overwrites the whole-lane verdict: its file
    carries a -scoped suffix instead. A seen-red-scoped file is only written
    for a run that carried the sentinel, because injected_selection adds it.
    """
    base = "seen-red" if inject_assertion else lane
    if scoped:
        base += "-scoped"
    return f"{base}.json"


def runs_deep_acceptance(lane: str, scoped: bool) -> bool:
    """Only a whole, unscoped deep-lane run drives the deep-acceptance child."""
    return lane == "deep" and not scoped


def coverage_confession(
    lane: str,
    marker_filter: str,
    selected_tests: list[str] | None = None,
    phase_confessions: list | None = None,
) -> list[dict[str, str]]:
    """Name every scope this invocation did not exercise.

    A deep run installs the product twice, and neither installation covers what
    the other one does, so each phase states its own gap and those statements
    are carried here beside the lane's own.
    """
    confession = [{"scope": "environment lane", "reason": "no environment lane is defined"}]
    if lane != "deep":
        confession.insert(0, {"scope": "locked-install and public-candidate deep scope", "reason": "runs only in the explicit deep lane"})
    if marker_filter:
        confession.insert(0, {"scope": "deep-marked tests", "reason": f'deselected by the pytest -m "{marker_filter}" override'})
    if selected_tests:
        confession.insert(0, {"scope": "nonselected fast tests", "reason": "this scoped invocation selected: " + ", ".join(selected_tests)})
    for stated in phase_confessions or ():
        if isinstance(stated, dict) and {"scope", "reason"} <= set(stated):
            confession.append({"scope": str(stated["scope"]), "reason": str(stated["reason"])})
    return confession


def terminate_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run([executable("taskkill"), "/PID", str(process.pid), "/T", "/F"], capture_output=True, text=True, check=False)
    else:
        os.killpg(process.pid, signal.SIGTERM)


def run_child(command: list[str], deadline: float, environment: dict[str, str]) -> tuple[int, str, bool]:
    options: dict = {"cwd": ROOT, "text": True, "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "env": environment}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, **options)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            terminate_tree(process)
            tail, _ = process.communicate(timeout=10)
            return 124, tail or "", True
        try:
            tail, _ = process.communicate(timeout=min(HEARTBEAT_SECONDS, remaining))
            return process.returncode, tail or "", False
        except subprocess.TimeoutExpired:
            # A retried wait loses no output on any interpreter: the whole
            # output arrives with the wait that completes, so the heartbeat
            # only reports that the child is still running.
            print(json.dumps({"event": "lane-heartbeat", "remaining_s": round(max(0, deadline - time.monotonic()), 1)}), flush=True)


def missing_pytest_result(reason: str) -> dict:
    return {
        "schema": "evorthon.pytest-result.v2",
        "exit_code": 2,
        "counts": {"passed": 0, "failed": 0, "errors": 1, "skipped": 0, "deselected": 0},
        "missing": True,
        "reason": reason,
    }


def bounded_log_tail(output: str) -> dict[str, object]:
    """Keep enough child output to diagnose a hard exit without retaining an unbounded log."""
    truncated = len(output) > LOG_TAIL_MAX_CHARS
    return {
        "max_chars": LOG_TAIL_MAX_CHARS,
        "text": output[-LOG_TAIL_MAX_CHARS:],
        "truncated": truncated,
    }


def read_inflight_test(path: pathlib.Path, run_id: str, started_at_ns: int) -> str:
    if not path.exists():
        raise ValueError("in-flight test state is missing")
    if path.stat().st_mtime_ns < started_at_ns:
        raise ValueError("in-flight test state predates this run")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("run_id") != run_id:
        raise ValueError("in-flight test state run identity does not match")
    nodeid = state.get("nodeid")
    if not isinstance(nodeid, str) or not nodeid:
        raise ValueError("in-flight test state has no node id")
    return nodeid


def is_pytest_timeout_hard_exit(code: int, output: str, timeout: tuple[int, str]) -> bool:
    """Recognise pytest-timeout's Windows thread-mode os._exit output, not any missing result."""
    return (
        code == 1
        and timeout[1] == "thread"
        and len(PYTEST_TIMEOUT_BANNER.findall(output)) >= 2
        and PYTEST_TIMEOUT_STACK.search(output) is not None
    )


def synthesize_pytest_timeout_result(
    code: int,
    output: str,
    timeout: tuple[int, str],
    inflight_path: pathlib.Path,
    run_id: str,
    started_at_ns: int,
) -> dict | None:
    """Recover the one Windows per-test path that exits before pytest can write its result."""
    if not is_pytest_timeout_hard_exit(code, output, timeout):
        return None
    try:
        nodeid = read_inflight_test(inflight_path, run_id, started_at_ns)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return {
        "schema": "evorthon.pytest-result.v2",
        "exit_code": code,
        "counts": {"passed": 0, "failed": 0, "errors": 1, "skipped": 0, "deselected": 0},
        "missing": True,
        "reason": "pytest-timeout thread hard exit before structured pytest result",
        "timeout": {"fired": True, "kind": "per-test"},
        "last_running_test": nodeid,
        "log_tail": bounded_log_tail(output),
    }


def resolve_pytest_result(
    result_path: pathlib.Path,
    run_id: str,
    started_at_ns: int,
    timeout: tuple[int, str],
    code: int,
    output: str,
    inflight_path: pathlib.Path,
) -> tuple[dict, bool]:
    """Read pytest's normal result or synthesize only its recognised Windows hard-exit path."""
    try:
        return read_pytest_result(result_path, run_id, started_at_ns, timeout), False
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        timeout_result = synthesize_pytest_timeout_result(
            code, output, timeout, inflight_path, run_id, started_at_ns
        )
        if timeout_result is not None:
            return timeout_result, True
        return missing_pytest_result(str(exc)), False


def timeout_verdict(timeout: tuple[int, str], per_test_fired: bool, global_fired: bool, global_s: int) -> dict:
    kind = "per-test" if per_test_fired else "global" if global_fired else "none"
    return {
        "per_test_s": timeout[0],
        "per_test_method": timeout[1],
        "global_s": global_s,
        "fired": kind != "none",
        "kind": kind,
        "deadline_enforced_by": "wrapper process tree",
    }


def read_pytest_result(path: pathlib.Path, run_id: str, started_at_ns: int, timeout: tuple[int, str]) -> dict:
    if not path.exists():
        raise ValueError("pytest result is missing")
    if path.stat().st_mtime_ns < started_at_ns:
        raise ValueError("pytest result predates this run")
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("run_id") != run_id:
        raise ValueError("pytest result run identity does not match")
    if (result.get("per_test_timeout_s"), result.get("per_test_timeout_method")) != timeout:
        raise ValueError("pytest result timeout contract does not match")
    return result


def deep_phase_confessions(detail: dict) -> list:
    """What the installation phases of this run said they did not cover."""
    deep = detail.get("deep_acceptance")
    stated = deep.get("not_exercised") if isinstance(deep, dict) else None
    return stated if isinstance(stated, list) else []


def bound_phases(result: dict, commit: str) -> list[dict]:
    """Read the installation phases one deep result carries, refusing an unbound one.

    Every phase binds to the commit under acceptance and to the wheel that run
    built. A phase record naming another commit or another wheel is refused
    here, so evidence assembled out of two runs cannot be read as one. A red
    result that failed before a phase ran carries none and stays readable, so
    its own detail still reaches the verdict.
    """
    phases = result.get("phases")
    if not isinstance(phases, list):
        raise ValueError("deep acceptance result carries no installation phases")
    if result.get("status") == "green" and not phases:
        raise ValueError("a green deep acceptance result runs at least one installation phase")
    wheel = (result.get("wheel") or {}).get("sha256")
    for phase in phases:
        origin = phase.get("origin") or {}
        if origin.get("source commit") != commit:
            raise ValueError("deep acceptance phase names another commit")
        if origin.get("wheel sha256") != wheel:
            raise ValueError("deep acceptance phase names another wheel")
    return phases


def read_deep_result(path: pathlib.Path, run_id: str, commit: str, started_at_ns: int) -> dict:
    if not path.exists():
        raise ValueError("deep acceptance result is missing")
    if path.stat().st_mtime_ns < started_at_ns:
        raise ValueError("deep acceptance result predates this run")
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("run_id") != run_id:
        raise ValueError("deep acceptance result run identity does not match")
    if result.get("commit") != commit:
        raise ValueError("deep acceptance result commit does not match")
    if result.get("terminal") is not True or result.get("status") not in {"green", "red"}:
        raise ValueError("deep acceptance result is not terminal")
    bound_phases(result, commit)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", choices=BUDGETS, default="fast")
    parser.add_argument("--inject-assertion", action="store_true")
    parser.add_argument("tests", nargs="*")
    args = parser.parse_args()
    commit = subprocess.check_output([executable("git"), "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    timeout = pytest_timeout_contract()
    run_id = uuid.uuid4().hex
    started_at_ns = time.time_ns()
    started = time.monotonic()
    selection = injected_selection(args.tests, args.inject_assertion)
    scoped = bool(selection)
    marker_filter = marker_filter_for(args.lane, scoped)
    budget = wall_budget(args.lane, scoped)
    deadline = started + budget
    result_path = ROOT / ".pytest-results" / f"{args.lane}-{run_id}.json"
    inflight_path = ROOT / ".pytest-results" / f"{args.lane}-{run_id}.inflight.json"
    environment = os.environ.copy()
    environment.update({
        "EVORTHON_PYTEST_RESULT": str(result_path),
        "EVORTHON_PYTEST_INFLIGHT": str(inflight_path),
        "EVORTHON_RUN_ID": run_id,
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    source_root = str(ROOT / "src")
    inherited_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root if not inherited_pythonpath else source_root + os.pathsep + inherited_pythonpath
    )
    pytest_command = [
        sys.executable, "-m", "pytest", "-q", "-p", "evorthon_data.pytest_reporter", "-p", "no:cacheprovider",
        f"--timeout={timeout[0]}", f"--timeout-method={timeout[1]}", "-m", marker_filter,
    ]
    if args.inject_assertion:
        pytest_command.append("--evorthon-inject-assertion")
    pytest_command.extend(selection)
    code, output, timed_out = run_child(pytest_command, deadline, environment)
    pytest_result, per_test_timeout_fired = resolve_pytest_result(
        result_path, run_id, started_at_ns, timeout, code, output, inflight_path
    )
    if pytest_result.get("missing") and code == 0:
        code = 2
    detail: dict = {
        "pytest": pytest_result,
        "pytest_timed_out": timed_out,
        "per_test_timeout_fired": per_test_timeout_fired,
    }
    if code == 0 and runs_deep_acceptance(args.lane, scoped):
        remaining = max(0, int(deadline - time.monotonic()))
        deep_result_path = VERDICTS / "deep-acceptance" / f"{run_id}.json"
        deep_command = [
            sys.executable, "scripts/deep_acceptance.py", "--commit", commit, "--deadline-seconds", str(remaining),
            "--run-id", run_id, "--result-path", str(deep_result_path),
        ]
        deep_started_at_ns = time.time_ns()
        deep_code, deep_output, deep_timed_out = run_child(deep_command, deadline, environment)
        output += deep_output
        detail["deep_timed_out"] = deep_timed_out
        try:
            deep_result = read_deep_result(deep_result_path, run_id, commit, deep_started_at_ns)
            detail["deep_acceptance"] = deep_result
            if deep_result["status"] != "green":
                code = deep_code or 1
            else:
                code = deep_code
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            detail["deep_acceptance"] = {"rejected": str(exc)}
            code = deep_code or 2
    duration = round(time.monotonic() - started, 3)
    final_name = verdict_file_name(args.lane, scoped, args.inject_assertion)
    lane = "seen-red" if args.inject_assertion else args.lane
    verdict = {
        "schema": "evorthon.lane-verdict.v3", "repo": "evorthon-data", "lane": lane,
        "commit": commit, "run_id": run_id,
        "command": [sys.executable, "scripts/run_tests.py", "--lane", args.lane] + (["--inject-assertion"] if args.inject_assertion else []) + selection,
        "duration_s": duration, "exit_code": code, "counts": pytest_result["counts"], "structured_execution": detail,
        "not_exercised": coverage_confession(
            args.lane, marker_filter, selection, deep_phase_confessions(detail)
        ),
        "timeout": timeout_verdict(
            timeout, per_test_timeout_fired, timed_out or detail.get("deep_timed_out", False), budget
        ),
        "verdict": "green" if code == 0 else "red",
    }
    VERDICTS.mkdir(parents=True, exist_ok=True)
    (VERDICTS / final_name).write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result_path.unlink(missing_ok=True)
    inflight_path.unlink(missing_ok=True)
    print(output, end="")
    print(json.dumps({"verdict": verdict["verdict"], "counts": verdict["counts"], "duration_s": duration, "run_id": run_id}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
