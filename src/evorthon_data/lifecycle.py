"""The one supported application route: the whole delivery lifecycle, in order.

This module composes the stages the product already owns into one run. It adds
no capability of its own. Every stage is driven through the function that owns
it, every external mechanism arrives as an injected port or runner, and every
value this route reports is read off the outcome the owning stage returned.

The order is the order a delivery takes. A use case is opened and taken in from
the artefacts in hand; a residual round carries what a named human confirmed in
bulk; the readiness of the record is read with the case facts the approved
verification case supplies; the gaps it leaves are projected as tracked work;
one segment is drafted into a product declaration, adjudicated and emitted, and
the approved items are dispatched; that segment's case is taken in, verified
against its whole contract, and, where an output fails, diagnosed, advised on,
disposed of by a named human, projected as an approved remedy and rerun on the
corrected candidate; finally a version is cut on the recomputed readiness
digest and a named human accepts it on the evidence the case declares.

Nothing here decides anything. The route states no readiness rule, no
verification status, no fault class, no disposition and no assurance class:
each is read back from the stage that decided it. It also knows nothing about
any particular engagement. The words, the documents, the artefacts and the
fixtures are what it is given, so the same route serves a modernisation and a
greenfield delivery without a branch of any kind.

A closed decision an earlier stage reports shapes which later stages are
driven. A diagnosis reports one where it has one, and each is a completed
diagnosis rather than a failure: the disclosure policy withheld the packet, or
the run failed on clauses answered over declared facts and named no output for
a packet to answer for. On either decision the advice, the disposition and the
corrected rerun of that run are recorded as not reached, with the decision as
the reason, and the run carries what is still open and the status the
verification reported on to the acceptance evidence and the version cut. The
acceptance of such a run is recorded as not reached too, naming that status,
because a use case a scenario reports as failing is not verified and there is
nothing for a named human to accept. The route reads every one of those words
off what the stage before it reported and states none of its own.

What the record says. One stage record is written per stage under the records
root, and one lifecycle record is returned naming every stage's outcome. Both
carry identities, digests, counts and the closed words a component owns. Where
a stage reports the place it wrote a record, that value is left out, so no path
reaches either. No declared value of an artefact, a row, a rationale or a piece
of advice is reported anywhere: every stage's own reporting surface is already
bounded, and this route narrows rather than widens it.

Refusals. A run refuses before any stage begins when a mechanism it needs was
not given, because a lifecycle never reaches for a provider, a tracker or a
build tool of its own. Every other refusal is the refusal of the stage that
raised it, carried back unchanged. One of those leaves as itself rather than as
a route refusal: where the adviser is asked over an external destination with
no authorization, or one the environment will not validate, the egress gateway
denies the call and its own denial leaves this run unchanged, because the
composition root may not reach the security component to name it.
"""
# evorthon-implements: EVD-README-040
# evorthon-implements: EVD-README-037
from __future__ import annotations

# evorthon-component: composition
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import composition
from .composition import CompositionError, RefusalReason

# The form one stage record declares, and the directory the records of one run
# are held under inside the engagement's own records.
LIFECYCLE_RECORD_FORM = "evorthon.lifecycle.stage.record.v1"
LIFECYCLE_DIRECTORY = "lifecycle"
STAGE_RECORD = "{stage}.md"

# The stages one run drives, in the order it drives them. The names are the
# record names too, so a reader finds a stage's record by the stage's name.
INTAKE_ROUND = "intake-round"
RESIDUAL_ROUND = "residual-round"
READINESS = "readiness"
GAP_PROJECTION = "gap-projection"
SEGMENT_GENERATION = "segment-generation"
CAMPAIGN_DISPATCH = "campaign-dispatch"
CASE_INTAKE = "case-intake"
VERIFICATION = "verification"
DIAGNOSIS = "diagnosis"
ADVICE = "advice"
REMEDIATION = "remediation"
CORRECTED_RERUN = "corrected-rerun"
ACCEPTANCE_EVIDENCE = "acceptance-evidence"
VERSION_CUT = "version-cut"
ACCEPTANCE = "acceptance"

STAGES: tuple[str, ...] = (
    INTAKE_ROUND,
    RESIDUAL_ROUND,
    READINESS,
    GAP_PROJECTION,
    SEGMENT_GENERATION,
    CAMPAIGN_DISPATCH,
    CASE_INTAKE,
    VERIFICATION,
    DIAGNOSIS,
    ADVICE,
    REMEDIATION,
    CORRECTED_RERUN,
    ACCEPTANCE_EVIDENCE,
    VERSION_CUT,
    ACCEPTANCE,
)

# The value labels that name where a stage wrote a record. A lifecycle record
# carries identities and digests, so these are the values it leaves out.
PLACE_LABELS = frozenset({"record", "records"})
# What a stage records when an earlier stage's own decision means this run
# never drove it. The stage is still recorded, so a reader sees the whole run
# and reads why the stage holds nothing rather than finding it missing.
REACHED_LABEL = "reached"
REASON_LABEL = "reason"
NOT_REACHED = "not reached"
# The label a run reads a case status back under, written by the stage that
# decided it: the corrected rerun where one ran, and the verification itself
# where the fault is still open.
STATUS_LABEL = "status"
# What the acceptance records when the case status this run carries is not the
# passing one. The status is the one the stage that decided it reported, so the
# reason says what this run found and states nothing of its own.
UNVERIFIED_SCENARIO = "the verification reported a scenario result of {status}"
# How one reported value is written into a stage record, and what stands in the
# record for a value that names nothing at all.
VALUE_LINE = "{label}: {text}"
LIST_SEPARATOR = "; "
NOTHING = composition.NOTHING
FLAG_WORDS = {True: "yes", False: "no"}
# The mechanisms a run is given, in the order a refusal names them.
MECHANISM_NAMES: tuple[str, ...] = (
    "session",
    "egress",
    "pinax_runner",
    "ergasterion_runner",
    "autobuild_runner",
    "capabilities",
)


@dataclass(frozen=True)
class LifecycleMechanisms:
    """Every external mechanism one run is given, and the only ones it uses.

    The session is the Koine co-worker the intake rounds run in and the egress
    is the model port the adviser is asked through; the three runners are the
    released delivery commands, and the capability report is what an
    environment says is installed. A run that is not given one of them refuses
    before it starts rather than building a default of its own.
    """

    session: object = None
    egress: object = None
    pinax_runner: object = None
    ergasterion_runner: object = None
    autobuild_runner: object = None
    capabilities: object = None

    @property
    def missing(self) -> tuple[str, ...]:
        """Name every mechanism this run was not given, in a stable order."""
        return tuple(name for name in MECHANISM_NAMES if getattr(self, name) is None)


@dataclass(frozen=True)
class UseCaseIntake:
    """The words, artefacts and answers one use case is opened and taken in from.

    ``declarations`` and ``confirmed`` are the recorded declarations the
    environment holds for what each round read: one pair of a declaration kind
    and its written fields per declaration, in the form the record route takes
    them. The rounds read the artefacts; the record holds the declarations.
    """

    header_parts: tuple[str, ...]
    readings: tuple = ()
    answers: object = None
    authorization: object = None
    declarations: tuple[tuple[str, Mapping[str, str]], ...] = ()
    confirmed: tuple[tuple[str, Mapping[str, str]], ...] = ()


@dataclass(frozen=True)
class TrackerRoute:
    """The tracker one run projects gaps and approved remedies onto."""

    actor_handle: str
    prefix: str
    repository: object = None


@dataclass(frozen=True)
class SegmentDelivery:
    """The one segment a run takes through the delivery routes.

    The declaration request, the seeds and the canonicalisation are declared
    values the caller resolved from the documents it holds. The selections are
    the already-approved, already-ready items the campaign may run, each
    written as the item, its readiness and its approval.
    """

    declaration_request: object
    proposal_reference: str
    drafted_by: str
    reviewer: str
    disposition: str
    generation_reference: str
    generation_actor: str
    estate_name: str
    profile: str
    harness: str
    target_repository: object
    seeds: tuple = ()
    canonicalisation: object = None
    selections: tuple[str, ...] = ()
    delivery_authority: object = None


@dataclass(frozen=True)
class CaseVerification:
    """The documents and logical identities one segment's case is verified through."""

    case_document: str
    material_document: str
    corrected_material_document: str
    evidence_identity: str
    candidate_identity: str
    corrected_candidate_identity: str
    output_id: str
    advice_document: str
    rationale_document: str
    adviser_route: object
    adviser_authority: str
    disposition: str
    decided_by: str
    iteration: str
    remedy_summary: str
    adviser_authorization: object = None


@dataclass(frozen=True)
class VersionAcceptance:
    """The words one version is cut and accepted in."""

    version_reference: str
    version_identity: str
    covered_segments: str
    projection_reference: str
    decision_identity: str
    decided_by: str
    rationale: str
    scenario_case_versions: str = ""
    packages: str = ""
    evidence: str = ""
    case_readings: str = ""


@dataclass(frozen=True)
class LifecycleStage:
    """One stage's outcome, as the values the stage that owns it reported."""

    name: str
    values: tuple[tuple[str, str], ...]

    def value(self, label: str) -> str:
        """Read back one value this stage reported, refusing one it did not."""
        for name, text in self.values:
            if name == label:
                return text
        raise _refuse(f"the {self.name} stage reported no {label}")


@dataclass(frozen=True)
class LifecycleRecord:
    """What one whole run did, stage by stage, by identity and digest."""

    form: str
    engagement_id: str
    use_case_id: str
    stages: tuple[LifecycleStage, ...]

    def stage(self, name: str) -> LifecycleStage:
        """Read back one stage of this run, refusing one it did not drive."""
        for held in self.stages:
            if held.name == name:
                return held
        raise _refuse(f"this run drove no {name} stage")


def _refuse(detail: str) -> CompositionError:
    return CompositionError(RefusalReason.MALFORMED_VALUE, detail)


def _text(value: object) -> str:
    """Write one reported value as the single line a record holds it on."""
    if isinstance(value, bool):
        return FLAG_WORDS[value]
    if isinstance(value, (list, tuple)):
        written = LIST_SEPARATOR.join(_text(item) for item in value)
        return written if written else NOTHING
    written = str(value)
    return written if written else NOTHING


def _values(result) -> tuple[tuple[str, str], ...]:
    """Read one route's reported values, leaving out where it wrote its record."""
    return tuple(
        (label, _text(value)) for label, value in result.values if label not in PLACE_LABELS
    )


def _stage(name: str, result) -> LifecycleStage:
    return LifecycleStage(name=name, values=_values(result))


def _not_reached(name: str, reason: str) -> LifecycleStage:
    """Return the record of one stage a closed decision meant this run never drove.

    The reason is the decision an earlier stage reported, carried through
    unchanged. This route states no decision of its own and never turns one
    into a refusal: a run whose diagnosis was withheld keeps going, and the
    stages that needed the withheld material say so.
    """
    return LifecycleStage(name=name, values=((REACHED_LABEL, NOT_REACHED), (REASON_LABEL, reason)))


def _reported(result, label: str) -> str:
    """Read one value a route reported, refusing a label it did not report."""
    for name, text in _values(result):
        if name == label:
            return text
    raise _refuse(f"a route reported no {label}")


def _hold(base: Path, engagement_id: str, stage: LifecycleStage) -> None:
    """Write one stage's outcome down under the records root."""
    place = (
        base
        / engagement_id
        / LIFECYCLE_DIRECTORY
        / STAGE_RECORD.format(stage=stage.name)
    )
    composition.store_case_record(
        place,
        {
            "form": LIFECYCLE_RECORD_FORM,
            "stage": stage.name,
            "outcome": tuple(
                VALUE_LINE.format(label=label, text=text) for label, text in stage.values
            ),
        },
    )


def _confirm(mechanisms: LifecycleMechanisms) -> LifecycleMechanisms:
    """Refuse a run that was not given a mechanism it drives, before any stage."""
    if not isinstance(mechanisms, LifecycleMechanisms):
        raise _refuse("a lifecycle run is given the mechanisms it drives")
    missing = mechanisms.missing
    if missing:
        raise _refuse("a lifecycle run is given every mechanism it drives: " + ", ".join(missing))
    return mechanisms


def case_facts(base: Path, verification: CaseVerification, *, status: str | None = None):
    """Read the case index readiness is given off the approved verification case.

    The datasets, the expected outputs and the checkpoints are the ones the
    case froze, each named by the identity the evidence carries, so readiness
    reads the evidence route's own case rather than a hand-written index. The
    status is the one a verification stage reported, or none before any stage
    has reported one.
    """
    case = composition.read_case(base, verification.case_document)
    named = case.case_id
    return {
        "case_datasets": tuple(
            f"{named}:{dataset.dataset_id}:{dataset.role.value}:{dataset.provenance.value}"
            for dataset in case.frozen_datasets
        ),
        "case_expected_outputs": tuple(
            f"{named}:{output.output_id}:{output.provenance.value}:{output.origin.value}"
            for output in case.expected_outputs
        ),
        "case_checkpoints": tuple(
            f"{named}:{checkpoint.checkpoint_id}" for checkpoint in case.lineage.checkpoints
        ),
        "case_statuses": () if status is None else (f"{named}:{status}",),
    }


def _round_values(round_outcome) -> tuple[tuple[str, str], ...]:
    """Read one intake round's outcome: what it read, what it left and who saw it.

    Every value is a count, an artefact identity, a template section name or a
    closed word. No fact's value and no artefact's text is read here.
    """
    return (
        ("facts", _text(len(round_outcome.facts))),
        (
            "artefacts read",
            _text([crossing.identifier for crossing in round_outcome.artefact_egress]),
        ),
        (
            "artefacts withheld",
            _text(
                [
                    crossing.identifier
                    for crossing in round_outcome.artefact_egress
                    if not crossing.crossed
                ]
            ),
        ),
        ("residual questions", _text(list(round_outcome.residual_questions))),
        ("review", _text(round_outcome.review.disposition.value)),
        ("review findings", _text(round_outcome.review.findings.identifier)),
        ("locator warnings", _text(len(round_outcome.locator_warnings))),
    )


def run_lifecycle(
    *,
    repository: object,
    root: object,
    mechanisms: LifecycleMechanisms,
    intake: UseCaseIntake,
    tracker: TrackerRoute,
    delivery: SegmentDelivery,
    verification: CaseVerification,
    acceptance: VersionAcceptance,
) -> LifecycleRecord:
    """Drive one whole delivery lifecycle and report what each stage decided."""
    _confirm(mechanisms)
    base = composition.records_root(repository, root)
    opened = composition.open_use_case(
        repository=repository, root=root, header_parts=intake.header_parts
    )
    engagement_id = _reported(opened, "engagement")
    use_case_id = _reported(opened, "use case")
    held: list[LifecycleStage] = []

    def keep(stage: LifecycleStage) -> LifecycleStage:
        _hold(base, engagement_id, stage)
        held.append(stage)
        return stage

    def replayed():
        return composition.load_use_case(repository, root, engagement_id, use_case_id)[0]

    def declare(written) -> None:
        for kind, fields in written or ():
            composition.record_fact(
                repository=repository,
                root=root,
                engagement_id=engagement_id,
                use_case_id=use_case_id,
                kind=kind,
                declared_fields=tuple(f"{name}={value}" for name, value in fields.items()),
            )

    first = mechanisms.session.run_intake_round(
        replayed(), intake.readings, authorization=intake.authorization
    )
    keep(LifecycleStage(name=INTAKE_ROUND, values=_round_values(first)))
    declare(intake.declarations)

    second = first.session.run_intake_round(
        replayed(),
        intake.readings,
        answers=intake.answers,
        authorization=intake.authorization,
    )
    keep(LifecycleStage(name=RESIDUAL_ROUND, values=_round_values(second)))
    declare(intake.confirmed)

    declared = case_facts(base, verification)
    keep(
        _stage(
            READINESS,
            composition.read_use_case_readiness(
                repository=repository,
                root=root,
                engagement_id=engagement_id,
                use_case_id=use_case_id,
                **declared,
            ),
        )
    )
    keep(
        _stage(
            GAP_PROJECTION,
            composition.project_use_case_gaps(
                repository=repository,
                root=root,
                engagement_id=engagement_id,
                use_case_id=use_case_id,
                actor_handle=tracker.actor_handle,
                prefix=tracker.prefix,
                tracker_repository=tracker.repository,
                runner=mechanisms.pinax_runner,
                **declared,
            ),
        )
    )

    keep(
        _stage(
            SEGMENT_GENERATION,
            composition.generate_segment_products(
                repository=repository,
                root=root,
                engagement_id=engagement_id,
                declaration_request=delivery.declaration_request,
                proposal_reference=delivery.proposal_reference,
                drafted_by=delivery.drafted_by,
                reviewer=delivery.reviewer,
                disposition=delivery.disposition,
                generation_reference=delivery.generation_reference,
                generation_actor=delivery.generation_actor,
                estate_name=delivery.estate_name,
                seeds=delivery.seeds,
                canonicalisation=delivery.canonicalisation,
                capabilities=mechanisms.capabilities,
                runner=mechanisms.ergasterion_runner,
            ),
        )
    )
    keep(
        _stage(
            CAMPAIGN_DISPATCH,
            composition.dispatch_approved_items(
                repository=delivery.target_repository,
                profile=delivery.profile,
                harness=delivery.harness,
                selections=delivery.selections,
                capabilities=mechanisms.capabilities,
                runner=mechanisms.autobuild_runner,
                delivery_authority=delivery.delivery_authority,
            ),
        )
    )

    case_route = {
        "repository": repository,
        "root": root,
        "engagement_id": engagement_id,
        "case_document": verification.case_document,
    }
    adapters = {
        "evidence_identity": verification.evidence_identity,
        "candidate_identity": verification.candidate_identity,
    }
    keep(
        _stage(
            CASE_INTAKE, composition.intake_verification_case(**case_route, **adapters)
        )
    )
    verified = keep(
        _stage(
            VERIFICATION,
            composition.verify_case(
                **case_route, material_document=verification.material_document, **adapters
            ),
        )
    )
    diagnosis = {
        "material_document": verification.material_document,
        "output_id": verification.output_id,
    }
    diagnosed = keep(
        _stage(
            DIAGNOSIS,
            composition.diagnose_case_failure(**case_route, **adapters, **diagnosis),
        )
    )
    # The diagnosis reports a closed decision wherever it has one: a packet the
    # disclosure policy withheld, or a run that failed with no output for a
    # packet to answer for. Either decision means there is no packet to advise
    # on, so the advice, the disposition and the corrected rerun of that run
    # are recorded as not reached with the decision as the reason, and the run
    # goes on to the acceptance evidence and the version cut with the case
    # still open. A diagnosis that reports no such decision carries a packet
    # that may be carried onward, and those three stages are driven.
    decision = composition.diagnosis_decision(diagnosed.values)
    if decision is not None:
        keep(_not_reached(ADVICE, decision))
        keep(_not_reached(REMEDIATION, decision))
        keep(_not_reached(CORRECTED_RERUN, decision))
        # No corrected run settled the case, so the status this run carries is
        # the one the verification reported. The fault is open and the reading
        # is told so rather than told nothing.
        status = verified.value(STATUS_LABEL)
    else:
        keep(
            _stage(
                ADVICE,
                composition.ask_case_adviser(
                    **case_route,
                    **adapters,
                    **diagnosis,
                    advice_document=verification.advice_document,
                    adviser_route=verification.adviser_route,
                    egress=mechanisms.egress,
                    required_authority=verification.adviser_authority,
                    authorization=verification.adviser_authorization,
                ),
            )
        )
        disposition = {
            "advice_document": verification.advice_document,
            "disposition": verification.disposition,
            "decided_by": verification.decided_by,
            "rationale_document": verification.rationale_document,
        }
        decided = keep(
            _stage(
                REMEDIATION,
                composition.record_remediation(
                    **case_route,
                    **disposition,
                    use_case_id=use_case_id,
                    actor_handle=tracker.actor_handle,
                    prefix=tracker.prefix,
                    tracker_repository=tracker.repository,
                    iteration=verification.iteration,
                    remedy_summary=verification.remedy_summary,
                    runner=mechanisms.pinax_runner,
                    **declared,
                ),
            )
        )
        rerun = keep(
            _stage(
                CORRECTED_RERUN,
                composition.rerun_remediation(
                    **case_route,
                    **disposition,
                    decision_identity=decided.value("decision"),
                    evidence_identity=verification.evidence_identity,
                    candidate_identity=verification.corrected_candidate_identity,
                    material_document=verification.corrected_material_document,
                    prior_candidate_identity=verification.candidate_identity,
                    prior_material_document=verification.material_document,
                ),
            )
        )
        status = rerun.value(STATUS_LABEL)
    keep(_stage(ACCEPTANCE_EVIDENCE, composition.read_acceptance_evidence(**case_route)))

    reached = case_facts(base, verification, status=status)
    reading = composition.read_use_case_readiness(
        repository=repository,
        root=root,
        engagement_id=engagement_id,
        use_case_id=use_case_id,
        **reached,
    )
    keep(
        _stage(
            VERSION_CUT,
            composition.cut_use_case_version(
                repository=repository,
                root=root,
                engagement_id=engagement_id,
                use_case_id=use_case_id,
                version_reference=acceptance.version_reference,
                covered_segments=acceptance.covered_segments,
                projection_reference=acceptance.projection_reference,
                readiness_digest=_reported(reading, "readiness digest"),
                scenario_case_versions=acceptance.scenario_case_versions,
                packages=acceptance.packages,
                evidence=acceptance.evidence,
                **reached,
            ),
        )
    )
    # A use case a scenario reports as failing is not verified, so a run whose
    # case status is not the passing one has nothing to accept. The stage is
    # recorded as not reached, naming the status the run carries, and the
    # acceptance route is not called at all. Where it is called, whatever it
    # refuses for is its own refusal and leaves this run as it stands.
    if status == composition.PASSED:
        keep(
            _stage(
                ACCEPTANCE,
                composition.record_use_case_acceptance(
                    repository=repository,
                    root=root,
                    engagement_id=engagement_id,
                    use_case_id=use_case_id,
                    version_identity=acceptance.version_identity,
                    decision_identity=acceptance.decision_identity,
                    decided_by=acceptance.decided_by,
                    rationale=acceptance.rationale,
                    case_readings=acceptance.case_readings,
                    **reached,
                ),
            )
        )
    else:
        keep(_not_reached(ACCEPTANCE, UNVERIFIED_SCENARIO.format(status=status)))
    return LifecycleRecord(
        form=LIFECYCLE_RECORD_FORM,
        engagement_id=engagement_id,
        use_case_id=use_case_id,
        stages=tuple(held),
    )


__all__ = [
    "ACCEPTANCE",
    "ACCEPTANCE_EVIDENCE",
    "ADVICE",
    "CAMPAIGN_DISPATCH",
    "CASE_INTAKE",
    "CORRECTED_RERUN",
    "CaseVerification",
    "DIAGNOSIS",
    "GAP_PROJECTION",
    "INTAKE_ROUND",
    "LIFECYCLE_DIRECTORY",
    "LIFECYCLE_RECORD_FORM",
    "LifecycleMechanisms",
    "LifecycleRecord",
    "LifecycleStage",
    "MECHANISM_NAMES",
    "NOT_REACHED",
    "PLACE_LABELS",
    "REACHED_LABEL",
    "READINESS",
    "REASON_LABEL",
    "REMEDIATION",
    "RESIDUAL_ROUND",
    "SEGMENT_GENERATION",
    "STAGES",
    "STATUS_LABEL",
    "SegmentDelivery",
    "TrackerRoute",
    "UNVERIFIED_SCENARIO",
    "UseCaseIntake",
    "VERIFICATION",
    "VERSION_CUT",
    "VersionAcceptance",
    "case_facts",
    "run_lifecycle",
]
