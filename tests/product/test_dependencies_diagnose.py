"""The diagnose route reports an installed version or an absence, never a required version."""
from __future__ import annotations

import json

from evorthon_data import cli, dependencies

# Deliberately arbitrary version strings. The route reports whatever metadata
# holds, so no published version may be baked into this proof.
PATCHED_VERSIONS = {"pinax-tracker": "1.2.3", "ergasterion-factory": "4.5.6"}
ABSENT_DISTRIBUTION = "autobuild-factory"


def patched_lookup(distribution):
    try:
        return PATCHED_VERSIONS[distribution]
    except KeyError:
        raise dependencies.PackageNotFoundError(distribution) from None


def test_diagnose_reports_a_version_or_an_absence_for_every_delivery_distribution(monkeypatch, capsys):
    monkeypatch.setattr(dependencies, "version", patched_lookup)

    exit_code = cli.main(["diagnose"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["product"] == "evorthon-data-harness"
    capabilities = payload["capabilities"]
    assert set(capabilities) == set(dependencies.DELIVERY_DISTRIBUTIONS)
    assert set(PATCHED_VERSIONS) | {ABSENT_DISTRIBUTION} == set(dependencies.DELIVERY_DISTRIBUTIONS)
    for distribution, expected in PATCHED_VERSIONS.items():
        assert capabilities[distribution] == {"installed": True, "version": expected}
    assert capabilities[ABSENT_DISTRIBUTION] == {"installed": False, "version": None}


def test_diagnose_reports_every_delivery_distribution_from_the_live_environment():
    capabilities = dependencies.installed_capabilities()

    assert set(capabilities) == set(dependencies.DELIVERY_DISTRIBUTIONS)
    for capability in capabilities.values():
        assert set(capability) == {"installed", "version"}
        assert isinstance(capability["installed"], bool)
        assert capability["installed"] == (capability["version"] is not None)
