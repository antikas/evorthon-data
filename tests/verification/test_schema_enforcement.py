"""Generated-projection and fail-closed contract enforcement tests."""
from __future__ import annotations

import copy
import subprocess
import sys
from dataclasses import fields, replace
from pathlib import Path

import pytest

import test_domain_contracts as domain_fixture
from evorthon_data.verification.domain import (
    AssuranceLevel,
    ComparisonDimension,
    DatasetRole,
    DiagnosticStrength,
    Identity,
    ParityClause,
    ReplayInput,
    RuleConstraint,
    RuleOperator,
    SchemaValueType,
    VerificationMode,
)
from evorthon_data.verification.domain.contracts import DatasetProvenance, EvidenceProvenance
from evorthon_data.verification.enforcement import (
    PolicyChangedAfterObservationError,
    SerializationError,
    UnknownFieldError,
    UnknownSchemaVersionError,
    VerificationContractError,
    deserialize_json,
    deserialize_record,
    ensure_policy_unchanged,
    inspect_verification_case,
    inspect_verification_record,
    observe_policy,
    schema_projection_drift,
    serialize_record,
    validate_verification_case,
)
from evorthon_data.verification.enforcement.schema import generated_projection_bytes, write_schema_projections


ROOT = Path(__file__).parents[2]
SCHEMA_DIRECTORY = ROOT / "docs" / "verification" / "schemas"


def case_fixture(strength: DiagnosticStrength = DiagnosticStrength.REPLAYABLE):
    """Return the shared contract fixture through the public semantic source."""
    return domain_fixture.case(VerificationMode.MODERNISATION, strength)


def synthetic_case_fixture(strength: DiagnosticStrength = DiagnosticStrength.REPLAYABLE):
    """Return a case whose every dataset and expected output is synthetic."""
    return domain_fixture.case(VerificationMode.MODERNISATION, strength, DatasetProvenance.SYNTHETIC)


def issue_codes(case) -> set[str]:
    return {issue.code for issue in inspect_verification_case(case).issues}


def test_generated_schema_and_serialization_projections_are_byte_stable_and_current():
    first = generated_projection_bytes()
    second = generated_projection_bytes()

    assert first == second
    assert schema_projection_drift(SCHEMA_DIRECTORY) == {}
    subprocess.run([sys.executable, "scripts/generate_verification_schemas.py"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/generate_verification_schemas.py", "--check"], cwd=ROOT, check=True)
    assert schema_projection_drift(SCHEMA_DIRECTORY) == {}


def test_stale_schema_projection_reddens_the_drift_gate(tmp_path):
    write_schema_projections(tmp_path)
    schema = tmp_path / "verification-domain.schema.json"
    schema.write_bytes(schema.read_bytes() + b"\n")

    assert schema_projection_drift(tmp_path) == {
        "verification-domain.schema.json": "projection differs from the versioned domain source"
    }
    result = subprocess.run(
        [sys.executable, "scripts/generate_verification_schemas.py", "--check", "--directory", str(tmp_path)],
        cwd=ROOT,
    )
    assert result.returncode == 1


def test_serialization_round_trip_and_unknown_schema_or_field_policy_fail_closed():
    original = case_fixture()
    serialized = serialize_record(original)

    assert deserialize_record(serialized) == original

    unknown_version = copy.deepcopy(serialized)
    unknown_version["schema_version"] = "evorthon.verification.domain.v999"
    with pytest.raises(UnknownSchemaVersionError, match="reject"):
        deserialize_record(unknown_version)

    unknown_envelope_field = copy.deepcopy(serialized)
    unknown_envelope_field["future_extension"] = True
    with pytest.raises(UnknownFieldError, match="reject"):
        deserialize_record(unknown_envelope_field)

    unknown_record_field = copy.deepcopy(serialized)
    unknown_record_field["record"]["future_extension"] = True
    with pytest.raises(UnknownFieldError, match="reject"):
        deserialize_record(unknown_record_field)


def test_case_allows_multiple_inputs_and_omits_unused_context_roles():
    original = case_fixture()
    first_input = next(dataset for dataset in original.frozen_datasets if dataset.role is DatasetRole.INPUT)
    second_input = replace(
        first_input,
        dataset_id="second-input-dataset",
        content_digest="sha256:second-input-content",
    )
    valid = replace(
        original,
        frozen_datasets=(
            *(dataset for dataset in original.frozen_datasets if dataset.role is not DatasetRole.PRIOR_STATE),
            second_input,
        ),
    )

    assert inspect_verification_case(valid).valid
    assert validate_verification_case(valid) is valid


def test_parity_comparison_shape_must_match_its_frozen_expected_output():
    original = case_fixture()
    parity = original.comparison_policy.clauses[0]
    comparison = parity.comparison
    changed_fields = list(comparison.schema.fields)
    changed_fields[2] = replace(
        changed_fields[2],
        value_type=SchemaValueType.STRING,
        precision=None,
        scale=None,
    )
    invalid = replace(
        original,
        comparison_policy=replace(
            original.comparison_policy,
            clauses=(
                replace(
                    parity,
                    comparison=replace(
                        comparison,
                        schema=replace(comparison.schema, fields=tuple(changed_fields)),
                    ),
                ),
                *original.comparison_policy.clauses[1:],
            ),
        ),
    )

    assert "oracle-shape-divergence" in issue_codes(invalid)
    with pytest.raises(VerificationContractError):
        validate_verification_case(invalid)


def test_standalone_records_receive_semantic_validation_on_both_wire_directions():
    original = case_fixture()
    invalid_claim = replace(
        original.assurance.environment_certificate_claims[0],
        assurance_level=AssuranceLevel.DECLARED,
    )
    invalid_policy = replace(
        original.comparison_policy,
        tolerances=(replace(original.comparison_policy.tolerances[0], upper_bound="NaN"),),
    )

    with pytest.raises(VerificationContractError, match="invalid-assurance"):
        serialize_record(invalid_claim)
    with pytest.raises(VerificationContractError, match="invalid-policy-bound"):
        serialize_record(invalid_policy)

    claim_envelope = serialize_record(original.assurance.environment_certificate_claims[0])
    claim_envelope["record"]["assurance_level"] = AssuranceLevel.DECLARED.value
    with pytest.raises(VerificationContractError, match="invalid-assurance"):
        deserialize_record(claim_envelope)

    policy_envelope = serialize_record(original.comparison_policy)
    policy_envelope["record"]["tolerances"][0]["upper_bound"] = "NaN"
    with pytest.raises(VerificationContractError, match="invalid-policy-bound"):
        deserialize_record(policy_envelope)


def test_standalone_dataset_and_lineage_apply_shape_and_graph_validation():
    original = case_fixture()
    dataset = original.frozen_datasets[0]
    invalid_dataset = replace(dataset, grain=replace(dataset.grain, key_fields=()))
    cyclic_lineage = replace(
        original.lineage,
        checkpoints=(
            replace(original.lineage.checkpoints[0], parent_ids=("daily-output",)),
            original.lineage.checkpoints[1],
        ),
    )

    with pytest.raises(VerificationContractError, match="ambiguous-grain"):
        serialize_record(invalid_dataset)
    with pytest.raises(VerificationContractError, match="cyclic-lineage"):
        serialize_record(cyclic_lineage)

    dataset_envelope = serialize_record(dataset)
    dataset_envelope["record"]["grain"]["key_fields"] = []
    with pytest.raises(VerificationContractError, match="ambiguous-grain"):
        deserialize_record(dataset_envelope)

    lineage_envelope = serialize_record(original.lineage)
    lineage_envelope["record"]["checkpoints"][0]["parent_ids"] = ["daily-output"]
    with pytest.raises(VerificationContractError, match="cyclic-lineage"):
        deserialize_record(lineage_envelope)


def _valid_standalone_records():
    case = case_fixture()
    schema = case.expected_outputs[0].schema
    grain = case.expected_outputs[0].grain
    canonicalisation = case.expected_outputs[0].canonicalisation
    comparison = case.comparison_policy.clauses[0].comparison
    evidence = domain_fixture.evidence
    identity = domain_fixture.identity
    actual = domain_fixture.ActualOutput(
        "daily-output",
        "v1",
        "sha256:actual-content",
        schema,
        grain,
        canonicalisation,
        12,
        "sha256:actual-format",
        "approved actual output",
    )
    outcome = domain_fixture.ClauseOutcome(
        "parity-outcome",
        "v1",
        identity("parity"),
        domain_fixture.ClauseFamily.PARITY,
        domain_fixture.VerificationStatus.PASS,
        (ComparisonDimension.VALUE,),
        (evidence("expected-value"),),
        (evidence("actual-value"),),
    )
    result = domain_fixture.VerificationResult(
        "candidate-run",
        "v1",
        identity(case.case_id),
        domain_fixture.CandidateIdentity("candidate", "v1", "sha256:candidate"),
        case.context,
        (
            domain_fixture.receipt(domain_fixture.ReceiptSubject.INPUT),
            domain_fixture.receipt(domain_fixture.ReceiptSubject.CONTEXT),
        ),
        (actual,),
        (outcome,),
        domain_fixture.VerificationStatus.PASS,
        (evidence("result-evidence"),),
        DiagnosticStrength.REPLAYABLE,
        domain_fixture.RepeatRunIdentity("repeat-run", "v1", "sha256:repeat-run"),
    )
    frontier = domain_fixture.LineageFrontier("prepared-input", (evidence("frontier"),))
    uncovered = domain_fixture.UncoveredPath(
        "prepared-to-output",
        ("prepared-input", "daily-output"),
        domain_fixture.UncoveredPathReason.MISSING_CHECKPOINT_EVIDENCE,
        (evidence("coverage-gap"),),
    )
    localisation = domain_fixture.DiagnosticLocalisation(
        "localisation",
        "v1",
        domain_fixture.LocalisationStatus.INFERRED,
        (frontier,),
        (domain_fixture.LineageFrontier("daily-output", (evidence("upper-frontier"),)),),
        (uncovered,),
        (evidence("localisation"),),
    )
    fault = domain_fixture.FaultRecord(
        "fault",
        "v1",
        identity(result.result_id),
        (outcome.outcome_id,),
        domain_fixture.FaultClass.CALCULATION_PRECISION_ROUNDING,
        localisation,
        "daily output calculation",
        domain_fixture.DisclosureDecision.DISCLOSE,
        (evidence("fault-support"),),
        (evidence("fault-contradiction"),),
        identity("calculation"),
    )
    advice = domain_fixture.RemediationAdvice(
        "advice",
        "v1",
        identity(fault.fault_id),
        ("rounding policy differs",),
        ("align the declared rounding policy",),
        (identity("rounding-regression"),),
        (evidence("advice-support"),),
        (evidence("advice-contradiction"),),
        ("the candidate identity is exact",),
        identity("acceptance-authority"),
        domain_fixture.AdviserConfidence.MEDIUM,
    )
    decision = domain_fixture.RemediationDecision(
        "decision",
        "v1",
        identity(advice.advice_id),
        domain_fixture.RemediationDisposition.REQUEST_MORE_EVIDENCE,
        identity("acceptance-authority"),
        evidence("decision-rationale"),
        None,
    )
    records = (
        identity("identity"),
        evidence("evidence"),
        schema.fields[0],
        schema,
        grain,
        canonicalisation,
        domain_fixture.synthetic_provenance("input"),
        case.frozen_datasets[0],
        case.expected_outputs[0],
        result.candidate,
        case.context,
        result.independent_receipts[0],
        result.repeat_run_identity,
        case.comparison_policy.clauses[1].requirement.constraints[0],
        case.comparison_policy.clauses[1].requirement,
        comparison.aggregates[0],
        comparison.ordering.fields[0],
        comparison.ordering,
        comparison.replay.inputs[0],
        comparison.replay,
        comparison,
        case.comparison_policy.tolerances[0],
        case.comparison_policy.exclusions[0],
        case.comparison_policy.warning_bands[0],
        *case.comparison_policy.clauses,
        case.comparison_policy,
        case.lineage.checkpoints[0],
        case.lineage.output_bindings[0],
        case.lineage,
        case.assurance.owner_presented_evidence[0],
        case.assurance.environment_certificate_claims[0],
        case.assurance,
        case,
        actual,
        outcome,
        frontier,
        uncovered,
        localisation,
        result,
        fault,
        advice,
        decision,
    )
    assert {type(record) for record in records} == set(domain_fixture.DOMAIN_RECORD_TYPES)
    return records


def test_every_exposed_record_has_standalone_semantics_and_round_trips():
    for record in _valid_standalone_records():
        assert deserialize_record(serialize_record(record)) == record, type(record).__name__


def test_blind_review_standalone_bypass_probes_all_fail_closed():
    case = case_fixture()
    checkpoint = case.lineage.checkpoints[0]
    parity = case.comparison_policy.clauses[0]
    invalid_records = (
        domain_fixture.RuleConstraint("field", RuleOperator.PRESENT, "forbidden-value"),
        domain_fixture.OrderingDeclaration("ordering", "v1", (), ()),
        replace(checkpoint, replay=replace(checkpoint.replay, transformation=domain_fixture.identity("wrong-transform"))),
        replace(parity, required_evidence=()),
        domain_fixture.VerificationResult(
            "result",
            "v1",
            domain_fixture.identity("case"),
            domain_fixture.CandidateIdentity("candidate", "v1", "sha256:candidate"),
            case.context,
            (),
            (),
            (),
            domain_fixture.VerificationStatus.PASS,
            (),
            DiagnosticStrength.OUTPUT_ONLY,
            domain_fixture.RepeatRunIdentity("repeat", "v1", "sha256:repeat"),
        ),
    )

    for record in invalid_records:
        with pytest.raises(VerificationContractError):
            serialize_record(record)


def test_direct_record_validation_rejects_runtime_values_outside_declared_contract_types():
    malformed = domain_fixture.ReplayInput("input-dataset", "not-a-dataset-role", False)

    malformed_report = inspect_verification_record(malformed)
    assert not malformed_report.valid
    assert "invalid-record-type" in {issue.code for issue in malformed_report.issues}
    with pytest.raises(VerificationContractError, match="invalid-record-type"):
        serialize_record(malformed)


def test_every_declared_field_type_mismatch_is_a_controlled_contract_refusal():
    for record in _valid_standalone_records():
        for field in fields(record):
            malformed = replace(record, **{field.name: object()})
            report = inspect_verification_record(malformed)

            assert not report.valid, f"{type(record).__name__}.{field.name}"
            assert "invalid-record-type" in {issue.code for issue in report.issues}
            with pytest.raises(VerificationContractError, match="invalid-record-type"):
                serialize_record(malformed)


def test_deserialization_boundary_refuses_non_mapping_and_invalid_utf8_inputs():
    for envelope in (None, [], {1: "not-a-contract-field"}):
        with pytest.raises(SerializationError):
            deserialize_record(envelope)

    with pytest.raises(SerializationError, match="not valid JSON"):
        deserialize_json(b"\xff")


def test_insufficient_evidence_result_can_record_missing_receipts_and_outputs_without_false_facts():
    case = case_fixture()
    outcome = domain_fixture.ClauseOutcome(
        "parity-outcome",
        "v1",
        domain_fixture.identity("parity"),
        domain_fixture.ClauseFamily.PARITY,
        domain_fixture.VerificationStatus.INSUFFICIENT_EVIDENCE,
        (ComparisonDimension.VALUE,),
        (),
        (),
    )
    result = domain_fixture.VerificationResult(
        "candidate-run",
        "v1",
        domain_fixture.identity(case.case_id),
        domain_fixture.CandidateIdentity("candidate", "v1", "sha256:candidate"),
        case.context,
        (),
        (),
        (outcome,),
        domain_fixture.VerificationStatus.INSUFFICIENT_EVIDENCE,
        (domain_fixture.evidence("missing-input-receipt"),),
        DiagnosticStrength.OUTPUT_ONLY,
        domain_fixture.RepeatRunIdentity("repeat", "v1", "sha256:repeat"),
    )

    assert deserialize_record(serialize_record(result)) == result


def test_replays_resolve_to_checkpoint_identity_and_optional_inputs_may_be_absent():
    original = case_fixture()
    parity = original.comparison_policy.clauses[0]
    ghost_replay = replace(parity.comparison.replay, checkpoint_id="ghost-checkpoint")
    ghost = replace(
        original,
        comparison_policy=replace(
            original.comparison_policy,
            clauses=(
                replace(parity, comparison=replace(parity.comparison, replay=ghost_replay)),
                *original.comparison_policy.clauses[1:],
            ),
        ),
    )
    checkpoint = original.lineage.checkpoints[0]
    mismatched_replay = replace(checkpoint.replay, transformation=domain_fixture.identity("different-transformation"))
    mismatch = replace(
        original,
        lineage=replace(
            original.lineage,
            checkpoints=(replace(checkpoint, replay=mismatched_replay), *original.lineage.checkpoints[1:]),
        ),
    )

    assert "unresolved-replay-checkpoint" in issue_codes(ghost)
    assert "invalid-replay" in issue_codes(mismatch)

    without_prior = replace(
        original,
        frozen_datasets=tuple(
            dataset for dataset in original.frozen_datasets if dataset.role is not DatasetRole.PRIOR_STATE
        ),
    )
    optional_prior = ReplayInput("prior-state-dataset", DatasetRole.PRIOR_STATE, False)
    checkpoint = without_prior.lineage.checkpoints[0]
    checkpoint_replay = replace(checkpoint.replay, inputs=(*checkpoint.replay.inputs, optional_prior))
    parity = without_prior.comparison_policy.clauses[0]
    comparison_replay = replace(parity.comparison.replay, inputs=(*parity.comparison.replay.inputs, optional_prior))
    optional = replace(
        without_prior,
        comparison_policy=replace(
            without_prior.comparison_policy,
            clauses=(
                replace(parity, comparison=replace(parity.comparison, replay=comparison_replay)),
                *without_prior.comparison_policy.clauses[1:],
            ),
        ),
        lineage=replace(
            without_prior.lineage,
            checkpoints=(replace(checkpoint, replay=checkpoint_replay), *without_prior.lineage.checkpoints[1:]),
        ),
    )

    assert inspect_verification_case(optional).valid


def test_terminal_checkpoint_shape_must_match_bound_expected_output():
    original = case_fixture()
    terminal = original.lineage.checkpoints[-1]
    changed_fields = list(terminal.schema.fields)
    changed_fields[2] = replace(
        changed_fields[2],
        value_type=SchemaValueType.STRING,
        precision=None,
        scale=None,
    )
    invalid_terminal = replace(
        terminal,
        schema=replace(terminal.schema, fields=tuple(changed_fields)),
    )
    invalid = replace(
        original,
        lineage=replace(
            original.lineage,
            checkpoints=(*original.lineage.checkpoints[:-1], invalid_terminal),
        ),
    )

    assert "terminal-shape-divergence" in issue_codes(invalid)
    with pytest.raises(VerificationContractError):
        validate_verification_case(invalid)


@pytest.mark.parametrize(
    ("name", "mutate", "expected_code"),
    [
        (
            "unresolved lineage parent",
            lambda case: replace(
                case,
                lineage=replace(
                    case.lineage,
                    checkpoints=(
                        case.lineage.checkpoints[0],
                        replace(case.lineage.checkpoints[1], parent_ids=("not-declared",)),
                    ),
                ),
            ),
            "unresolved-lineage-parent",
        ),
        (
            "cyclic lineage",
            lambda case: replace(
                case,
                lineage=replace(
                    case.lineage,
                    checkpoints=(
                        replace(case.lineage.checkpoints[0], parent_ids=("daily-output",)),
                        case.lineage.checkpoints[1],
                    ),
                ),
            ),
            "cyclic-lineage",
        ),
        (
            "missing input role",
            lambda case: replace(
                case,
                frozen_datasets=tuple(dataset for dataset in case.frozen_datasets if dataset.role is not DatasetRole.INPUT),
            ),
            "missing-dataset-roles",
        ),
        (
            "missing expected outcome",
            lambda case: replace(case, expected_outputs=()),
            "missing-expected-outcomes",
        ),
        (
            "ambiguous output grain",
            lambda case: replace(
                case,
                expected_outputs=(
                    replace(case.expected_outputs[0], grain=replace(case.expected_outputs[0].grain, key_fields=("customer-id", "customer-id"))),
                ),
            ),
            "ambiguous-grain",
        ),
        (
            "missing clause evidence",
            lambda case: replace(
                case,
                comparison_policy=replace(
                    case.comparison_policy,
                    clauses=(replace(case.comparison_policy.clauses[0], required_evidence=()), *case.comparison_policy.clauses[1:]),
                ),
            ),
            "missing-evidence",
        ),
        (
            "unknown policy target",
            lambda case: replace(
                case,
                comparison_policy=replace(
                    case.comparison_policy,
                    tolerances=(replace(case.comparison_policy.tolerances[0], clause_ids=("not-a-clause",)),),
                ),
            ),
            "invalid-policy-scope",
        ),
        (
            "invalid assurance claim",
            lambda case: replace(
                case,
                assurance=replace(
                    case.assurance,
                    declared_level=AssuranceLevel.ENVIRONMENT_CERTIFIED,
                    environment_certificate_claims=(),
                ),
            ),
            "invalid-assurance",
        ),
    ],
    ids=lambda case: case,
)
def test_case_refusal_fixtures_cover_the_declared_fail_closed_conditions(name, mutate, expected_code):
    invalid = mutate(case_fixture())

    assert expected_code in issue_codes(invalid), name
    with pytest.raises(VerificationContractError):
        validate_verification_case(invalid)


@pytest.mark.parametrize(
    ("name", "mutate_provenance"),
    [
        ("no generator record", lambda provenance: None),
        ("no seed", lambda provenance: replace(provenance, seed="")),
        ("no generator identity", lambda provenance: replace(provenance, generator_id="")),
        ("no generator version", lambda provenance: replace(provenance, generator_version="")),
    ],
)
def test_synthetic_dataset_without_a_complete_generator_record_fails_closed(name, mutate_provenance):
    original = synthetic_case_fixture()
    dataset = original.frozen_datasets[0]
    incomplete = replace(dataset, synthetic_provenance=mutate_provenance(dataset.synthetic_provenance))
    invalid = replace(original, frozen_datasets=(incomplete, *original.frozen_datasets[1:]))

    assert "incomplete-synthetic-provenance" in issue_codes(invalid), name
    with pytest.raises(VerificationContractError, match="incomplete-synthetic-provenance"):
        validate_verification_case(invalid)
    with pytest.raises(VerificationContractError, match="incomplete-synthetic-provenance"):
        serialize_record(incomplete)


@pytest.mark.parametrize("provenance", (DatasetProvenance.REAL, DatasetProvenance.DERIVED))
def test_non_synthetic_dataset_carrying_a_generator_record_fails_closed(provenance):
    original = case_fixture()
    dataset = original.frozen_datasets[0]
    contradiction = replace(
        dataset,
        provenance=provenance,
        synthetic_provenance=domain_fixture.synthetic_provenance("input"),
    )
    invalid = replace(original, frozen_datasets=(contradiction, *original.frozen_datasets[1:]))

    assert "contradictory-dataset-provenance" in issue_codes(invalid)
    with pytest.raises(VerificationContractError, match="contradictory-dataset-provenance"):
        validate_verification_case(invalid)
    with pytest.raises(VerificationContractError, match="contradictory-dataset-provenance"):
        serialize_record(contradiction)


def test_fully_synthetic_case_validates_with_no_refusal_and_round_trips():
    synthetic = synthetic_case_fixture()

    report = inspect_verification_case(synthetic)

    assert report.issues == ()
    assert report.valid
    assert validate_verification_case(synthetic) is synthetic
    assert deserialize_record(serialize_record(synthetic)) == synthetic
    assert synthetic.expected_outputs[0].origin.value == "synthetic-derivation"


@pytest.mark.parametrize(
    ("name", "build", "expected"),
    [
        ("real", lambda: case_fixture(), EvidenceProvenance.REAL),
        ("synthetic", lambda: synthetic_case_fixture(), EvidenceProvenance.SYNTHETIC),
        (
            "mixed",
            lambda: replace(
                synthetic_case_fixture(),
                frozen_datasets=(
                    domain_fixture.frozen_dataset(DatasetRole.INPUT),
                    *synthetic_case_fixture().frozen_datasets[1:],
                ),
            ),
            EvidenceProvenance.MIXED,
        ),
    ],
)
def test_validation_output_labels_evidence_provenance_and_never_refuses_on_it(name, build, expected):
    report = inspect_verification_case(build())

    assert report.valid, name
    assert report.evidence_provenance is expected
    assert inspect_verification_record(case_fixture().frozen_datasets[0]).evidence_provenance is None


def test_comparison_policy_cannot_change_after_observation():
    original = case_fixture()
    observation = observe_policy(original)
    changed = replace(
        original,
        comparison_policy=replace(original.comparison_policy, digest="sha256:policy-after-observation"),
    )

    with pytest.raises(PolicyChangedAfterObservationError, match="changed after observation"):
        ensure_policy_unchanged(changed, observation)


@pytest.mark.parametrize(
    ("name", "mutate_policy"),
    [
        (
            "clause",
            lambda policy: replace(
                policy,
                clauses=(
                    replace(policy.clauses[0], required_evidence=(domain_fixture.evidence("changed-clause-evidence"),)),
                    *policy.clauses[1:],
                ),
            ),
        ),
        ("tolerance", lambda policy: replace(policy, tolerances=(replace(policy.tolerances[0], upper_bound="0.04"),))),
        (
            "exclusion",
            lambda policy: replace(
                policy,
                exclusions=(
                    replace(
                        policy.exclusions[0],
                        selector=(RuleConstraint("record-state", RuleOperator.EQUALS, "active"),),
                    ),
                ),
            ),
        ),
        ("warning band", lambda policy: replace(policy, warning_bands=(replace(policy.warning_bands[0], lower_bound="0.02"),))),
    ],
)
def test_policy_content_cannot_change_after_observation_when_declared_digest_is_unchanged(name, mutate_policy):
    original = case_fixture()
    observation = observe_policy(original)
    changed_policy = mutate_policy(original.comparison_policy)
    changed = replace(original, comparison_policy=changed_policy)

    assert changed_policy.digest == observation.policy_digest, name
    with pytest.raises(PolicyChangedAfterObservationError, match="changed after observation"):
        ensure_policy_unchanged(changed, observation)


@pytest.mark.parametrize("non_finite", ("Infinity", "-Infinity", "NaN"))
def test_non_finite_policy_bounds_fail_closed_with_structured_issues(non_finite):
    original = case_fixture()
    invalid_tolerance = replace(
        original,
        comparison_policy=replace(
            original.comparison_policy,
            tolerances=(replace(original.comparison_policy.tolerances[0], upper_bound=non_finite),),
        ),
    )
    invalid_warning = replace(
        original,
        comparison_policy=replace(
            original.comparison_policy,
            warning_bands=(replace(original.comparison_policy.warning_bands[0], upper_bound=non_finite),),
        ),
    )

    assert "invalid-policy-bound" in issue_codes(invalid_tolerance)
    assert "invalid-policy-bound" in issue_codes(invalid_warning)


def test_exclusion_selector_must_resolve_to_a_target_comparison_field():
    original = case_fixture()
    invalid = replace(
        original,
        comparison_policy=replace(
            original.comparison_policy,
            exclusions=(
                replace(
                    original.comparison_policy.exclusions[0],
                    selector=(RuleConstraint("misspelled-field", RuleOperator.EQUALS, "suppressed"),),
                ),
            ),
        ),
    )

    assert "unresolved-exclusion-field" in issue_codes(invalid)
    with pytest.raises(VerificationContractError):
        validate_verification_case(invalid)


@pytest.mark.parametrize(
    ("clause_index", "target_field"),
    ((1, "contract"), (2, "invariant"), (3, "operational_signal"), (4, "delivery_artifact")),
)
def test_non_parity_clause_targets_require_complete_identities(clause_index, target_field):
    original = case_fixture()
    clauses = list(original.comparison_policy.clauses)
    clauses[clause_index] = replace(clauses[clause_index], **{target_field: Identity("declared-target", "", "")})
    invalid = replace(original, comparison_policy=replace(original.comparison_policy, clauses=tuple(clauses)))

    assert "invalid-clause-target" in issue_codes(invalid)


def test_assurance_presenter_and_certificate_issuer_require_complete_identities():
    original = case_fixture()
    invalid = replace(
        original,
        assurance=replace(
            original.assurance,
            owner_presented_evidence=(
                replace(original.assurance.owner_presented_evidence[0], presented_by=Identity("data-owner", "", "")),
            ),
            environment_certificate_claims=(
                replace(
                    original.assurance.environment_certificate_claims[0],
                    issued_by=Identity("environment-assurer", "", ""),
                ),
            ),
        ),
    )

    codes = issue_codes(invalid)
    assert "invalid-owner-evidence" in codes
    assert "invalid-assurance" in codes


def test_unknown_assurance_level_fails_closed_in_validation_and_serialization():
    original = case_fixture()
    invalid = replace(original, assurance=replace(original.assurance, declared_level="unsupported"))

    assert "invalid-assurance" in issue_codes(invalid)
    with pytest.raises(VerificationContractError):
        validate_verification_case(invalid)
    with pytest.raises(VerificationContractError):
        serialize_record(invalid)


def _case_with_multi_clause_policy_scope():
    original = case_fixture()
    primary = original.comparison_policy.clauses[0]
    secondary_comparison = replace(
        primary.comparison,
        schema=replace(
            primary.comparison.schema,
            fields=tuple(field for field in primary.comparison.schema.fields if field.field_id != "daily-value"),
        ),
        aggregates=(),
        replay=None,
    )
    secondary = ParityClause(
        "parity-secondary",
        "v1",
        primary.expected_output_id,
        secondary_comparison,
        primary.required_evidence,
    )
    return original, primary, secondary


@pytest.mark.parametrize(
    ("policy_field", "expected_code"),
    (
        ("tolerances", "invalid-tolerance"),
        ("exclusions", "unresolved-exclusion-field"),
        ("warning_bands", "invalid-warning-band"),
    ),
)
def test_multiclause_policy_fields_must_resolve_in_every_target_clause(policy_field, expected_code):
    original, primary, secondary = _case_with_multi_clause_policy_scope()
    if policy_field == "tolerances":
        policy_value = (
            replace(
                original.comparison_policy.tolerances[0],
                clause_ids=(primary.clause_id, secondary.clause_id),
                dimensions=(ComparisonDimension.VALUE,),
            ),
        )
    elif policy_field == "exclusions":
        policy_value = (
            replace(
                original.comparison_policy.exclusions[0],
                clause_ids=(primary.clause_id, secondary.clause_id),
                selector=(RuleConstraint("daily-value", RuleOperator.EQUALS, "suppressed"),),
            ),
        )
    else:
        policy_value = (
            replace(
                original.comparison_policy.warning_bands[0],
                clause_ids=(primary.clause_id, secondary.clause_id),
            ),
        )
    invalid = replace(
        original,
        comparison_policy=replace(
            original.comparison_policy,
            clauses=(primary, secondary, *original.comparison_policy.clauses[1:]),
            **{policy_field: policy_value},
        ),
    )

    assert expected_code in issue_codes(invalid)
    with pytest.raises(VerificationContractError):
        validate_verification_case(invalid)


@pytest.mark.parametrize(
    ("identity_field", "expected_code"),
    (
        ("expected_state", "invalid-checkpoint"),
        ("transformation", "invalid-checkpoint"),
        ("provenance", "invalid-checkpoint"),
    ),
)
def test_checkpoint_identities_require_identifier_version_and_digest(identity_field, expected_code):
    original = case_fixture()
    checkpoint = original.lineage.checkpoints[0]
    invalid_checkpoint = replace(
        checkpoint,
        **{identity_field: replace(getattr(checkpoint, identity_field), version="", digest="")},
    )
    invalid = replace(original, lineage=replace(original.lineage, checkpoints=(invalid_checkpoint, *original.lineage.checkpoints[1:])))

    assert expected_code in issue_codes(invalid)
    with pytest.raises(VerificationContractError):
        serialize_record(invalid)


@pytest.mark.parametrize("identity_field", ("replay", "context", "transformation"))
def test_replay_identities_require_complete_immutable_facts(identity_field):
    original = case_fixture()
    checkpoint = original.lineage.checkpoints[0]
    replay = checkpoint.replay
    assert replay is not None
    if identity_field == "replay":
        invalid_replay = replace(replay, version="")
    elif identity_field == "context":
        invalid_replay = replace(replay, context=replace(replay.context, version="", digest=""))
    else:
        invalid_replay = replace(replay, transformation=replace(replay.transformation, version="", digest=""))
    invalid_checkpoint = replace(checkpoint, replay=invalid_replay)
    invalid = replace(original, lineage=replace(original.lineage, checkpoints=(invalid_checkpoint, *original.lineage.checkpoints[1:])))

    assert "invalid-replay" in issue_codes(invalid)
    with pytest.raises(VerificationContractError):
        serialize_record(invalid)


def test_checkpointed_case_requires_a_terminal_for_each_expected_output():
    original = case_fixture(DiagnosticStrength.CHECKPOINTED)
    invalid = replace(
        original,
        lineage=replace(
            original.lineage,
            output_bindings=(replace(original.lineage.output_bindings[0], terminal_checkpoint_id=None),),
        ),
    )

    assert "missing-output-terminal" in issue_codes(invalid)
