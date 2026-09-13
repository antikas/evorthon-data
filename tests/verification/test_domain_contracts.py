# evorthon-verifies: EVD-README-019
from dataclasses import fields, replace

import pytest

from evorthon_data.verification.domain import (
    ActualOutput,
    AdviserConfidence,
    AggregateControl,
    AssuranceDeclaration,
    AssuranceLevel,
    CandidateIdentity,
    CanonicalisationDeclaration,
    Checkpoint,
    CLAUSE_TYPE_BY_FAMILY,
    ClauseFamily,
    ClauseOutcome,
    ComparisonDeclaration,
    ComparisonDimension,
    ComparisonPolicy,
    ConformanceClause,
    ContextIdentity,
    DOMAIN_ENUM_TYPES,
    DOMAIN_FIELD_INVENTORY,
    DOMAIN_RECORD_TYPES,
    DOMAIN_TYPE_VERSIONS,
    DatasetRole,
    DeliveryIntegrityClause,
    DisclosureDecision,
    DiagnosticLocalisation,
    DiagnosticStrength,
    EnvironmentCertificateClaim,
    EvidenceReference,
    ExclusionDeclaration,
    ExpectedOutput,
    ExpectedOutputOrigin,
    FaultClass,
    FaultRecord,
    FrozenDataset,
    GrainDeclaration,
    Identity,
    IndependentlyDerivedReceipt,
    InvariantClause,
    LineageDefinition,
    LineageFrontier,
    LocalisationStatus,
    NullPlacement,
    OperationalEvidenceClause,
    OrderingDeclaration,
    OrderingField,
    OutputLineageBinding,
    OwnerPresentedEvidence,
    ParityClause,
    ReceiptSubject,
    RemediationAdvice,
    RemediationDecision,
    RemediationDisposition,
    RepeatRunIdentity,
    ReplayInput,
    ReplaySpecification,
    RuleConstraint,
    RuleDeclaration,
    RuleOperator,
    SchemaDeclaration,
    SchemaField,
    SchemaValueType,
    SortDirection,
    ToleranceDeclaration,
    UncoveredPath,
    UncoveredPathReason,
    VERIFICATION_DOMAIN_VERSION,
    VerificationCase,
    VerificationMode,
    VerificationResult,
    VerificationStatus,
    WarningBandDeclaration,
)
from evorthon_data.verification.domain.contracts import (
    DatasetProvenance,
    EvidenceProvenance,
    SyntheticProvenance,
)


def identity(name: str) -> Identity:
    return Identity(identifier=name, version="v1", digest=f"sha256:{name}")


def evidence(name: str) -> EvidenceReference:
    return EvidenceReference(evidence_id=name, version="v1", digest=f"sha256:{name}", summary=f"approved {name}")


def receipt(subject: ReceiptSubject) -> IndependentlyDerivedReceipt:
    return IndependentlyDerivedReceipt(
        receipt_id=f"{subject.value}-receipt",
        version="v1",
        subject=subject,
        subject_identity=identity(f"{subject.value}-subject"),
        observed_digest=f"sha256:{subject.value}-observed",
        derived_by=identity("evidence-repository"),
        evidence=(evidence(f"{subject.value}-receipt-evidence"),),
    )


def schema() -> SchemaDeclaration:
    return SchemaDeclaration(
        schema_id="daily-output-schema",
        version="v1",
        fields=(
            SchemaField("business-date", SchemaValueType.DATE, False, "effective-date", None, None),
            SchemaField("customer-id", SchemaValueType.STRING, False, "business-key", None, None),
            SchemaField("daily-value", SchemaValueType.DECIMAL, False, "measure", 18, 2),
            SchemaField("record-state", SchemaValueType.STRING, False, "publication-state", None, None),
        ),
        format_name="csv-rfc4180",
    )


def grain() -> GrainDeclaration:
    return GrainDeclaration(
        grain_id="customer-day",
        version="v1",
        key_fields=("business-date", "customer-id"),
        population_description="one approved customer-day population",
        duplicate_keys_permitted=False,
    )


def canonicalisation() -> CanonicalisationDeclaration:
    return CanonicalisationDeclaration(
        canonicalisation_id="canonical-json-v1",
        version="v1",
        unicode_normalisation="NFC",
        null_representation="json-null",
        decimal_scale=2,
        timestamp_precision="milliseconds",
        timezone="UTC",
        signed_zero_representation="positive-zero",
        non_finite_number_policy="reject",
    )


def synthetic_provenance(name: str) -> SyntheticProvenance:
    return SyntheticProvenance(
        generator_id="declared-schema-generator",
        generator_version="v1",
        seed=f"seed:{name}",
        constraints_digest=f"sha256:{name}-constraints",
        constrained_by=(identity("real-reference-extract"),),
    )


def frozen_dataset(role: DatasetRole, provenance: DatasetProvenance = DatasetProvenance.REAL) -> FrozenDataset:
    return FrozenDataset(
        dataset_id=f"{role.value}-dataset",
        version="v1",
        role=role,
        provenance=provenance,
        synthetic_provenance=(
            synthetic_provenance(role.value) if provenance is DatasetProvenance.SYNTHETIC else None
        ),
        content_digest=f"sha256:{role.value}-content",
        schema=schema(),
        grain=grain(),
        canonicalisation=canonicalisation(),
        row_count=12,
        approved_summary=f"approved {role.value} summary",
    )


def requirement(name: str) -> RuleDeclaration:
    return RuleDeclaration(
        rule_id=name,
        version="v1",
        constraints=(RuleConstraint("verification-status", RuleOperator.PRESENT, None),),
    )


def comparison(replay: ReplaySpecification | None) -> ComparisonDeclaration:
    return ComparisonDeclaration(
        comparison_id="daily-output-comparison",
        version="v1",
        dimensions=tuple(ComparisonDimension),
        schema=schema(),
        grain=grain(),
        canonicalisation=canonicalisation(),
        aggregates=(
            AggregateControl(
                "daily-total",
                "v1",
                "sum",
                "daily-value",
                "daily-value-total",
                ("business-date",),
                "exclude-null",
                "half-even",
            ),
        ),
        ordering=OrderingDeclaration(
            "daily-output-order",
            "v1",
            (
                OrderingField("business-date", SortDirection.ASCENDING, NullPlacement.LAST),
                OrderingField("customer-id", SortDirection.ASCENDING, NullPlacement.LAST),
            ),
            ("business-date", "customer-id"),
        ),
        replay=replay,
    )


def clauses(replay: ReplaySpecification | None):
    required = (evidence("rule-evidence"),)
    return (
        ParityClause("parity", "v1", "daily-output", comparison(replay), required),
        ConformanceClause("conformance", "v1", identity("interface-contract"), requirement("interface-rule"), required),
        InvariantClause("invariant", "v1", identity("balance-invariant"), requirement("balance-rule"), required),
        OperationalEvidenceClause("operational", "v1", identity("run-complete"), requirement("run-rule"), required),
        DeliveryIntegrityClause("integrity", "v1", identity("delivery-artifact"), requirement("integrity-rule"), required),
    )


def policy(replay: ReplaySpecification | None) -> ComparisonPolicy:
    return ComparisonPolicy(
        policy_id="comparison-policy",
        version="v1",
        digest="sha256:policy",
        clauses=clauses(replay),
        tolerances=(
            ToleranceDeclaration(
                "daily-value-tolerance",
                "v1",
                ("parity",),
                (ComparisonDimension.VALUE, ComparisonDimension.AGGREGATE),
                ("daily-value", "daily-value-total"),
                "absolute-difference",
                "0.00",
                "0.05",
                "currency-units",
                "half-even",
            ),
        ),
        exclusions=(
            ExclusionDeclaration(
                "suppressed-record-exclusion",
                "v1",
                ("parity",),
                (ComparisonDimension.POPULATION,),
                (RuleConstraint("record-state", RuleOperator.EQUALS, "suppressed"),),
                "approved suppressed records do not form part of the published population",
            ),
        ),
        warning_bands=(
            WarningBandDeclaration(
                "daily-value-warning",
                "v1",
                ("parity",),
                (ComparisonDimension.VALUE,),
                ("daily-value",),
                "absolute-difference",
                "0.01",
                "0.05",
                "currency-units",
            ),
        ),
    )


def case(
    mode: VerificationMode,
    strength: DiagnosticStrength,
    provenance: DatasetProvenance = DatasetProvenance.REAL,
) -> VerificationCase:
    context = ContextIdentity("context", "v1", "sha256:context", "2026-09-02T09:00:00Z", "09:00", "UTC")
    replay = (
        ReplaySpecification(
            "replay",
            "v1",
            "prepared-input",
            (ReplayInput("input-dataset", DatasetRole.INPUT, True),),
            context,
            identity("prepare-input"),
            schema(),
            grain(),
            canonicalisation(),
        )
        if strength is DiagnosticStrength.REPLAYABLE
        else None
    )
    checkpoints = (
        ()
        if strength is DiagnosticStrength.OUTPUT_ONLY
        else (
            Checkpoint(
                checkpoint_id="prepared-input",
                version="v1",
                parent_ids=(),
                expected_state=identity("prepared-input-expected"),
                schema=schema(),
                grain=grain(),
                canonicalisation=canonicalisation(),
                transformation=identity("prepare-input"),
                provenance=identity("candidate-source"),
                diagnostic_evidence=(evidence("checkpoint-evidence"),),
                replay=replay,
            ),
            Checkpoint(
                checkpoint_id="daily-output",
                version="v1",
                parent_ids=("prepared-input",),
                expected_state=identity("daily-output-expected"),
                schema=schema(),
                grain=grain(),
                canonicalisation=canonicalisation(),
                transformation=identity("publish-daily-output"),
                provenance=identity("candidate-source"),
                diagnostic_evidence=(evidence("output-checkpoint-evidence"),),
                replay=None,
            ),
        )
    )
    origin = (
        ExpectedOutputOrigin.MODERNISATION_CAPTURE
        if mode is VerificationMode.MODERNISATION
        else ExpectedOutputOrigin.GREENFIELD_SPECIFICATION
    )
    if provenance is DatasetProvenance.SYNTHETIC:
        origin = ExpectedOutputOrigin.SYNTHETIC_DERIVATION
    return VerificationCase(
        case_id=f"{mode.value}-{strength.value}",
        version="v1",
        mode=mode,
        frozen_datasets=tuple(frozen_dataset(role, provenance) for role in DatasetRole),
        expected_outputs=(
            ExpectedOutput(
                output_id="daily-output",
                version="v1",
                origin=origin,
                provenance=provenance,
                content_digest="sha256:expected-content",
                schema=schema(),
                grain=grain(),
                canonicalisation=canonicalisation(),
                row_count=12,
                format_digest="sha256:expected-format",
                approved_summary="approved expected daily output",
            ),
        ),
        context=context,
        comparison_policy=policy(replay),
        lineage=LineageDefinition(
            "lineage",
            "v1",
            checkpoints,
            (
                OutputLineageBinding(
                    "daily-output",
                    None if strength is DiagnosticStrength.OUTPUT_ONLY else "daily-output",
                ),
            ),
        ),
        assurance=AssuranceDeclaration(
            assurance_id="assurance",
            version="v1",
            declared_level=AssuranceLevel.OWNER_PRESENTED,
            owner_presented_evidence=(
                OwnerPresentedEvidence(
                    "owner-evidence", "v1", "sha256:owner-evidence", identity("data-owner"), evidence("approval")
                ),
            ),
            environment_certificate_claims=(
                EnvironmentCertificateClaim(
                    "certificate-claim",
                    "v1",
                    "sha256:certificate",
                    identity("environment-assurer"),
                    AssuranceLevel.ENVIRONMENT_CERTIFIED,
                ),
            ),
        ),
        diagnostic_strength=strength,
    )


@pytest.mark.parametrize("mode", list(VerificationMode))
@pytest.mark.parametrize("strength", list(DiagnosticStrength))
def test_case_contract_constructs_output_only_checkpointed_and_replayable_cases_for_both_modes(mode, strength):
    verification_case = case(mode, strength)

    assert verification_case.mode is mode
    assert verification_case.diagnostic_strength is strength
    assert {dataset.role for dataset in verification_case.frozen_datasets} == set(DatasetRole)
    assert verification_case.expected_outputs[0].origin is (
        ExpectedOutputOrigin.MODERNISATION_CAPTURE
        if mode is VerificationMode.MODERNISATION
        else ExpectedOutputOrigin.GREENFIELD_SPECIFICATION
    )
    assert bool(verification_case.lineage.checkpoints) is not (strength is DiagnosticStrength.OUTPUT_ONLY)
    output_binding = verification_case.lineage.output_bindings[0]
    assert output_binding.expected_output_id == "daily-output"
    assert output_binding.terminal_checkpoint_id == (
        None if strength is DiagnosticStrength.OUTPUT_ONLY else "daily-output"
    )
    if output_binding.terminal_checkpoint_id is not None:
        assert output_binding.terminal_checkpoint_id in {
            checkpoint.checkpoint_id for checkpoint in verification_case.lineage.checkpoints
        }
    assert (
        verification_case.lineage.checkpoints[0].replay is not None
        if verification_case.lineage.checkpoints
        else False
    ) is (strength is DiagnosticStrength.REPLAYABLE)


def test_case_model_shares_contracts_without_a_shared_or_candidate_oracle():
    modernisation = case(VerificationMode.MODERNISATION, DiagnosticStrength.OUTPUT_ONLY)
    greenfield = case(VerificationMode.GREENFIELD, DiagnosticStrength.OUTPUT_ONLY)

    assert type(modernisation) is type(greenfield) is VerificationCase
    assert modernisation.expected_outputs[0].origin is ExpectedOutputOrigin.MODERNISATION_CAPTURE
    assert greenfield.expected_outputs[0].origin is ExpectedOutputOrigin.GREENFIELD_SPECIFICATION
    assert "candidate" not in DOMAIN_FIELD_INVENTORY["VerificationCase"]
    assert "candidate" in DOMAIN_FIELD_INVENTORY["VerificationResult"]


def test_parity_contract_declares_the_complete_comparison_oracle_and_policy():
    verification_case = case(VerificationMode.MODERNISATION, DiagnosticStrength.REPLAYABLE)
    parity = verification_case.comparison_policy.clauses[0]

    assert isinstance(parity, ParityClause)
    assert set(parity.comparison.dimensions) == set(ComparisonDimension)
    assert parity.comparison.grain.key_fields == ("business-date", "customer-id")
    assert parity.comparison.schema.fields[2].value_type is SchemaValueType.DECIMAL
    assert parity.comparison.canonicalisation.decimal_scale == 2
    assert parity.comparison.aggregates[0].operation == "sum"
    assert parity.comparison.ordering is not None
    assert parity.comparison.replay is not None
    assert verification_case.comparison_policy.tolerances[0].upper_bound == "0.05"
    assert verification_case.comparison_policy.exclusions[0].selector[0].expected_value == "suppressed"
    assert verification_case.comparison_policy.warning_bands[0].lower_bound == "0.01"
    for type_name in ("ToleranceDeclaration", "ExclusionDeclaration", "WarningBandDeclaration"):
        assert not any(field_name.endswith("_digest") for field_name in DOMAIN_FIELD_INVENTORY[type_name])


def test_clause_families_have_separate_domain_contract_types():
    assert set(CLAUSE_TYPE_BY_FAMILY) == set(ClauseFamily)
    assert set(CLAUSE_TYPE_BY_FAMILY.values()) == {
        ParityClause,
        ConformanceClause,
        InvariantClause,
        OperationalEvidenceClause,
        DeliveryIntegrityClause,
    }


def test_result_records_per_clause_outcomes_and_fault_localisation_frontiers():
    verification_case = case(VerificationMode.MODERNISATION, DiagnosticStrength.CHECKPOINTED)
    outcome = ClauseOutcome(
        "parity-outcome",
        "v1",
        identity("parity"),
        ClauseFamily.PARITY,
        VerificationStatus.FAIL,
        (ComparisonDimension.VALUE,),
        (evidence("expected-value"),),
        (evidence("actual-value"),),
    )
    result = VerificationResult(
        "candidate-run",
        "v1",
        identity(verification_case.case_id),
        CandidateIdentity("candidate", "v8", "sha256:candidate"),
        verification_case.context,
        (
            receipt(ReceiptSubject.INPUT),
            receipt(ReceiptSubject.REFERENCE),
            receipt(ReceiptSubject.PRIOR_STATE),
            receipt(ReceiptSubject.CONTEXT),
        ),
        (
            ActualOutput(
                "daily-output",
                "v1",
                "sha256:actual-content",
                schema(),
                grain(),
                canonicalisation(),
                12,
                "sha256:actual-format",
                "approved actual summary",
            ),
        ),
        (outcome,),
        VerificationStatus.FAIL,
        (evidence("result-evidence"),),
        DiagnosticStrength.CHECKPOINTED,
        RepeatRunIdentity("repeat-candidate-run", "v1", "sha256:repeat-candidate-run"),
    )
    localisation = DiagnosticLocalisation(
        "lineage-localisation",
        "v1",
        LocalisationStatus.INFERRED,
        (LineageFrontier("prepared-input", (evidence("last-confirmed-match"),)),),
        (LineageFrontier("daily-output", (evidence("first-observed-difference"),)),),
        (
            UncoveredPath(
                "input-to-output",
                ("prepared-input", "daily-output"),
                UncoveredPathReason.MISSING_CHECKPOINT_EVIDENCE,
                (evidence("coverage-gap"),),
            ),
        ),
        (evidence("localisation-evidence"),),
    )
    fault = FaultRecord(
        "daily-output-fault",
        "v1",
        identity(result.result_id),
        (outcome.outcome_id,),
        FaultClass.CALCULATION_PRECISION_ROUNDING,
        localisation,
        "daily-output aggregate and value comparison",
        DisclosureDecision.DISCLOSE,
        (evidence("fault-evidence"),),
        (evidence("contradicting-fault-evidence"),),
        identity("report-calculation"),
    )

    assert result.clause_outcomes == (outcome,)
    assert fault.localisation.status is LocalisationStatus.INFERRED
    assert fault.localisation.lower_frontier[0].checkpoint_id == "prepared-input"
    assert fault.localisation.upper_frontier[0].checkpoint_id == "daily-output"
    assert fault.localisation.uncovered_paths[0].reason is UncoveredPathReason.MISSING_CHECKPOINT_EVIDENCE
    assert {receipt.subject for receipt in result.independent_receipts} == {
        ReceiptSubject.INPUT,
        ReceiptSubject.REFERENCE,
        ReceiptSubject.PRIOR_STATE,
        ReceiptSubject.CONTEXT,
    }
    assert result.repeat_run_identity.digest == "sha256:repeat-candidate-run"
    assert fault.fault_class is FaultClass.CALCULATION_PRECISION_ROUNDING
    assert fault.disclosure_decision is DisclosureDecision.DISCLOSE
    assert fault.contradicting_evidence[0].evidence_id == "contradicting-fault-evidence"


def test_advice_retains_contradictions_assumptions_authority_confidence_and_evidence_request():
    advice = RemediationAdvice(
        "advice",
        "v1",
        identity("daily-output-fault"),
        ("rounding policy differs between the candidate and expected output",),
        ("align the declared rounding policy",),
        (identity("rounding-regression"),),
        (evidence("supporting-advice-evidence"),),
        (evidence("contradicting-advice-evidence"),),
        ("the declared candidate identity represents the executed artefact",),
        identity("data-platform-acceptance-authority"),
        AdviserConfidence.MEDIUM,
    )
    decision = RemediationDecision(
        "remediation",
        "v1",
        identity(advice.advice_id),
        RemediationDisposition.REQUEST_MORE_EVIDENCE,
        identity("data-platform-acceptance-authority"),
        evidence("evidence-request-rationale"),
        None,
    )

    assert advice.contradicting_evidence[0].evidence_id == "contradicting-advice-evidence"
    assert advice.assumptions == ("the declared candidate identity represents the executed artefact",)
    assert advice.required_authority.identifier == "data-platform-acceptance-authority"
    assert advice.confidence is AdviserConfidence.MEDIUM
    assert decision.disposition is RemediationDisposition.REQUEST_MORE_EVIDENCE
    assert decision.approved_work is None


def test_owner_presented_evidence_and_environment_certificate_claims_are_distinct_contracts():
    verification_case = case(VerificationMode.MODERNISATION, DiagnosticStrength.CHECKPOINTED)
    owner_evidence = verification_case.assurance.owner_presented_evidence[0]
    certificate_claim = verification_case.assurance.environment_certificate_claims[0]

    assert type(owner_evidence) is OwnerPresentedEvidence
    assert type(certificate_claim) is EnvironmentCertificateClaim
    assert not isinstance(owner_evidence, EnvironmentCertificateClaim)
    assert set(DOMAIN_FIELD_INVENTORY["OwnerPresentedEvidence"]) != set(
        DOMAIN_FIELD_INVENTORY["EnvironmentCertificateClaim"]
    )


def test_dataset_provenance_classes_and_synthetic_derivation_origin_are_declared():
    assert {member.value for member in DatasetProvenance} == {"real", "synthetic", "derived"}
    assert {member.value for member in EvidenceProvenance} == {"real", "mixed", "synthetic"}
    assert ExpectedOutputOrigin.SYNTHETIC_DERIVATION.value == "synthetic-derivation"
    assert DOMAIN_FIELD_INVENTORY["SyntheticProvenance"] == (
        "generator_id",
        "generator_version",
        "seed",
        "constraints_digest",
        "constrained_by",
    )
    assert "provenance" in DOMAIN_FIELD_INVENTORY["FrozenDataset"]
    assert "synthetic_provenance" in DOMAIN_FIELD_INVENTORY["FrozenDataset"]
    assert "provenance" in DOMAIN_FIELD_INVENTORY["ExpectedOutput"]


def test_synthetic_dataset_carries_generator_seed_constraints_and_constraining_identities():
    synthetic = frozen_dataset(DatasetRole.INPUT, DatasetProvenance.SYNTHETIC)
    real = frozen_dataset(DatasetRole.REFERENCE)

    assert synthetic.provenance is DatasetProvenance.SYNTHETIC
    assert synthetic.synthetic_provenance.generator_id == "declared-schema-generator"
    assert synthetic.synthetic_provenance.generator_version == "v1"
    assert synthetic.synthetic_provenance.seed == "seed:input"
    assert synthetic.synthetic_provenance.constraints_digest == "sha256:input-constraints"
    assert synthetic.synthetic_provenance.constrained_by[0].identifier == "real-reference-extract"
    assert real.provenance is DatasetProvenance.REAL
    assert real.synthetic_provenance is None


def test_case_derives_evidence_provenance_from_every_dataset_and_expected_output():
    real = case(VerificationMode.MODERNISATION, DiagnosticStrength.OUTPUT_ONLY)
    synthetic = case(VerificationMode.MODERNISATION, DiagnosticStrength.OUTPUT_ONLY, DatasetProvenance.SYNTHETIC)
    mixed = replace(
        synthetic,
        frozen_datasets=(frozen_dataset(DatasetRole.INPUT), *synthetic.frozen_datasets[1:]),
    )
    derived = replace(
        real,
        frozen_datasets=tuple(
            replace(dataset, provenance=DatasetProvenance.DERIVED) for dataset in real.frozen_datasets
        ),
    )

    assert real.evidence_provenance is EvidenceProvenance.REAL
    assert synthetic.evidence_provenance is EvidenceProvenance.SYNTHETIC
    assert mixed.evidence_provenance is EvidenceProvenance.MIXED
    assert derived.evidence_provenance is EvidenceProvenance.MIXED
    assert "evidence_provenance" not in DOMAIN_FIELD_INVENTORY["VerificationCase"]


def test_portable_contract_inventory_has_no_mutable_source_or_sensitive_access_fields():
    forbidden_fields = {
        "location",
        "source_location",
        "source_path",
        "uri",
        "url",
        "endpoint",
        "credential",
        "secret",
        "raw_rows",
    }
    portable_fields = {field_name for field_names in DOMAIN_FIELD_INVENTORY.values() for field_name in field_names}

    assert not portable_fields & forbidden_fields
    assert "uncovered_paths" in DOMAIN_FIELD_INVENTORY["DiagnosticLocalisation"]


def test_field_and_version_inventories_are_mechanical_projections_of_the_semantic_source():
    contract_types = (*DOMAIN_RECORD_TYPES, *DOMAIN_ENUM_TYPES)

    assert set(DOMAIN_FIELD_INVENTORY) == {record_type.__name__ for record_type in DOMAIN_RECORD_TYPES}
    assert all(
        DOMAIN_FIELD_INVENTORY[record_type.__name__] == tuple(field.name for field in fields(record_type))
        for record_type in DOMAIN_RECORD_TYPES
    )
    assert VERIFICATION_DOMAIN_VERSION == "evorthon.verification.domain.v2"
    assert set(DOMAIN_TYPE_VERSIONS) == {contract_type.__name__ for contract_type in contract_types}
    assert all(
        DOMAIN_TYPE_VERSIONS[contract_type.__name__] == "evorthon.verification.domain.v2"
        for contract_type in contract_types
    )
    assert set(DOMAIN_TYPE_VERSIONS.values()) == {VERIFICATION_DOMAIN_VERSION}
