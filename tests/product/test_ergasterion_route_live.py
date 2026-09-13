"""Live proofs of the Ergasterion generation route against the installed wheel.

Every delivery-tool import happens inside a test body or through
``pytest.importorskip``: the public candidate imports this module without the
released wheels present.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

from evorthon_data.delivery import (
    ErgasterionGenerationRoute,
    ErgasterionRouteError,
    ExactGenerationContract,
    FixtureSeed,
    GenerationDisposition,
    ProductDeclaration,
    SubprocessErgasterionRunner,
)
from evorthon_data.delivery.ergasterion import REQUIRED_COMMANDS
from evorthon_data.verification.domain import CanonicalisationDeclaration, Identity

PRODUCER_DECLARATION = """product:
  name: settled_positions
  domain: risk
  version: "1.0"
  layer: derived
  owner: platform-team

sources:
  - contract: risk.position_feed@1
    kind: fixture
    fixture:
      relation: raw_risk_position_feed
      fields:
        - {name: position_id, type: string}
        - {name: booked_at, type: timestamp}
    expect:
      fields: [position_id, booked_at]

steps:
  - pattern: batch_transfer
  - pattern: data_validation
    on_failure: quarantine
    error_threshold: 0.01
    rules:
      - field: position_id
        completeness: 1.0
  - pattern: calculated_fields
    fields:
      - {name: booked_on, type: date, expression: "CAST(booked_at AS DATE)"}
      - name: exposure_amount
        type: {name: decimal, precision: 18, scale: 2}
        expression: "CAST(1 AS NUMERIC)"
  - pattern: data_contracts
  - pattern: lineage_capture
  - pattern: metadata_capture
    description: "Settled positions published for exposure reporting."
    ownership: platform-team
  - pattern: schema_publish
  - pattern: data_publish
    publication_mode: atomic

target:
  shape: declared
  contract:
    freshness: "daily by 06:00 UTC"
    access:
      classification: internal

checkpointing:
  granularity: step
  max_retries: 2
  backoff: fixed
  checkpoint: true
"""

CONSUMER_DECLARATION = """product:
  name: exposure_summary
  domain: risk
  version: "1.0"
  layer: derived
  owner: platform-team

sources:
  - contract: risk.settled_positions@{major}
    expect:
      fields: [position_id, booked_on]

steps:
  - pattern: batch_transfer
  - pattern: data_validation
    on_failure: quarantine
    error_threshold: 0.01
    rules:
      - field: position_id
        completeness: 1.0
  - pattern: calculated_fields
    fields:
      - {{name: exposure_label, type: string, expression: "'settled'"}}
  - pattern: data_contracts
  - pattern: lineage_capture
  - pattern: metadata_capture
    description: "Exposure summary published for risk reporting."
    ownership: platform-team
  - pattern: schema_publish
  - pattern: data_publish
    publication_mode: atomic

target:
  shape: declared
  contract:
    freshness: "daily by 06:00 UTC"
    access:
      classification: internal

checkpointing:
  granularity: step
  max_retries: 2
  backoff: fixed
"""

SEED_TABLE = "position_id,booked_at\np-1,2026-01-01T00:00:00\np-2,2026-01-02T00:00:00\n"
CANONICALISATION = CanonicalisationDeclaration(
    canonicalisation_id="risk-canonicalisation",
    version="v1",
    unicode_normalisation="NFC",
    null_representation="empty",
    decimal_scale=2,
    timestamp_precision="second",
    timezone="UTC",
    signed_zero_representation="unsigned",
    non_finite_number_policy="rejected",
)
ACTOR = "generation-actor"


def released_command() -> tuple[str, ...]:
    """The released entry point this environment holds."""
    found = shutil.which("ergasterion")
    return (found,) if found else (sys.executable, "-m", "ergasterion")


def capability_report() -> dict:
    from evorthon_data.dependencies import installed_capabilities

    return installed_capabilities()


def generation_contract(*, major: int = 1) -> ExactGenerationContract:
    return ExactGenerationContract(
        identity=Identity(
            identifier="risk-settlement-generation",
            version="v1",
            digest="sha256:approved-generation-digest",
        ),
        declarations=(
            ProductDeclaration("settled_positions.yml", PRODUCER_DECLARATION),
            ProductDeclaration("exposure_summary.yml", CONSUMER_DECLARATION.format(major=major)),
        ),
        seeds=(FixtureSeed("raw_risk_position_feed.csv", SEED_TABLE),),
        canonicalisation=CANONICALISATION,
    )


def live_route() -> ErgasterionGenerationRoute:
    return ErgasterionGenerationRoute(
        SubprocessErgasterionRunner(command=released_command()),
        actor=ACTOR,
        capabilities=capability_report(),
    )


def table_rows(estate: Path, relative: str) -> list[list[str]]:
    rows = list(csv.reader((estate / relative).read_text(encoding="utf-8").splitlines()))
    return rows[1:]


@pytest.fixture(scope="module")
def generation(tmp_path_factory):
    pytest.importorskip("ergasterion")
    estate = tmp_path_factory.mktemp("generation") / "estate"
    return live_route().generate(generation_contract(), estate=estate), estate


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_compatibility_contract_passes_against_the_installed_wheel():
    pytest.importorskip("ergasterion")
    report = capability_report()

    assert report["ergasterion-factory"]["installed"] is True
    assert live_route().assert_supported() == REQUIRED_COMMANDS


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_declared_fixture_backed_source_is_accepted_and_emitted(generation):
    result, estate = generation

    assert sorted(path.name for path in (estate / "declarations/products").iterdir()) == [
        "exposure_summary.yml",
        "settled_positions.yml",
    ]
    assert (estate / "seeds/raw_risk_position_feed.csv").read_text(encoding="utf-8") == SEED_TABLE
    assert dict(result.artefact_digests)["graphs/products/product-graph.json"].startswith("sha256:")


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_the_emitted_graph_maps_into_a_domain_lineage_definition(generation):
    result, estate = generation
    description = json.loads((estate / "graphs/products/product-graph.json").read_text(encoding="utf-8"))

    assert len(result.graph.nodes) == len(table_rows(estate, "graphs/products/product-nodes.csv"))
    assert len(result.graph.edges) == len(table_rows(estate, "graphs/products/product-edges.csv"))
    assert len(result.graph.field_lineage) == len(
        table_rows(estate, "graphs/products/product-field-lineage.csv")
    )
    assert [checkpoint.checkpoint_id for checkpoint in result.lineage.checkpoints] == description[
        "checkpoint_relations"
    ]
    assert [entry.relation for entry in result.auxiliary_lineage] == [
        entry["relation"] for entry in description["auxiliary_relations"]
    ]

    checkpoint = result.lineage.checkpoints[0]
    published = json.loads(
        (estate / "contracts/products/risk/settled_positions/contract.json").read_text(encoding="utf-8")
    )
    assert checkpoint.checkpoint_id == "risk.settled_positions"
    assert checkpoint.version == f"v{published['identity']['major']}"
    assert [field_.field_id for field_ in checkpoint.schema.fields] == [
        field_["name"] for field_ in published["relations"][0]["fields"]
    ]
    assert result.lineage.output_bindings[0].expected_output_id == "risk.exposure_summary"
    assert result.lineage.output_bindings[0].terminal_checkpoint_id == "risk.settled_positions"


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_repeated_generation_from_one_contract_yields_identical_bytes_and_digests(generation, tmp_path):
    first, first_estate = generation
    second = live_route().generate(generation_contract(), estate=tmp_path / "repeat")

    assert first.artefact_digests == second.artefact_digests
    for relative, _ in first.artefact_digests:
        assert (first_estate / relative).read_bytes() == (tmp_path / "repeat" / relative).read_bytes()


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_a_consumer_major_mismatch_is_red_against_the_emitted_estate(tmp_path):
    pytest.importorskip("ergasterion")

    with pytest.raises(ErgasterionRouteError, match=r"pin risk.settled_positions@2 does not match"):
        live_route().generate(generation_contract(major=2), estate=tmp_path / "mismatch")


@pytest.mark.deep
@pytest.mark.timeout(300)
def test_generated_artefacts_are_referenced_only_after_a_distinct_reviewer_adjudicates(generation):
    result, _ = generation
    reviewer = Identity(identifier="generation-reviewer", version="r1", digest="sha256:review-digest")

    with pytest.raises(ErgasterionRouteError, match="after an accepted adjudication"):
        result.adjudicated(
            reviewer=reviewer, disposition=GenerationDisposition.PENDING
        ).build_evidence()
    evidence = result.adjudicated(
        reviewer=reviewer, disposition=GenerationDisposition.ACCEPTED
    ).build_evidence()

    assert reviewer.identifier != result.generated_by
    assert len(evidence) == len(result.artefact_digests)
