"""Structured pytest outcome capture used by the repository verdict wrapper."""
from __future__ import annotations

# evorthon-component: presentation

import json
import os
from pathlib import Path

import pytest


def write_json(destination: str, data: dict) -> None:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def pytest_addoption(parser):
    parser.addoption("--evorthon-inject-assertion", action="store_true")


def pytest_sessionfinish(session, exitstatus):
    destination = os.environ.get("EVORTHON_PYTEST_RESULT")
    if not destination:
        return
    stats = session.config.pluginmanager.get_plugin("terminalreporter").stats
    counts = {
        "passed": len(stats.get("passed", [])),
        "failed": len(stats.get("failed", [])),
        "errors": len(stats.get("error", [])),
        "skipped": len(stats.get("skipped", [])),
        "deselected": len(stats.get("deselected", [])),
    }
    data = {
        "schema": "evorthon.pytest-result.v2",
        "exit_code": int(exitstatus),
        "counts": counts,
        "run_id": os.environ.get("EVORTHON_RUN_ID"),
        "per_test_timeout_s": int(session.config.getini("timeout")),
        "per_test_timeout_method": session.config.getini("timeout_method"),
    }
    write_json(destination, data)


def clear_inflight_state(destination: str, run_id: str | None, nodeid: str) -> None:
    """Remove only the completed protocol's state, leaving a hard-exit record intact."""
    path = Path(destination)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return
    if state.get("run_id") == run_id and state.get("nodeid") == nodeid:
        path.unlink(missing_ok=True)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Persist current identity before inner protocol hooks can arm a timeout timer."""
    destination = os.environ.get("EVORTHON_PYTEST_INFLIGHT")
    if destination:
        run_id = os.environ.get("EVORTHON_RUN_ID")
        write_json(destination, {"schema": "evorthon.pytest-inflight.v1", "run_id": run_id, "nodeid": item.nodeid})
    yield
    if destination:
        clear_inflight_state(destination, os.environ.get("EVORTHON_RUN_ID"), item.nodeid)
