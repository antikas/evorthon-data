"""The diagnostic adviser: what crosses the port, what comes back, what is refused."""
from __future__ import annotations

import ast
import builtins
import importlib
import inspect as introspection
import os
import runpy
import subprocess
from dataclasses import is_dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path

import pytest

import test_fault_packet as packets
import test_privacy_gate as gate_fixture
from evorthon_data.security import (
    AuthorizationValidation,
    EgressDenialReason,
    ModelCall,
    ModelCallPurpose,
    ModelDestination,
    ModelEgressAuthorization,
    ModelEgressDenied,
    ModelEgressGateway,
    ModelEgressMode,
)
from evorthon_data.verification.core.canonical import canonical_digest, record_digest
from evorthon_data.verification.core.fault import build_fault_packet, packet_fields
from evorthon_data.verification.domain.contracts import (
    AdviserConfidence,
    DisclosureDecision,
    EvidenceReference,
    Identity,
    RemediationAdvice,
)
from evorthon_data.verification.enforcement.privacy import (
    PACKET_BOUNDS,
    GatedFaultPacket,
    PrivacyRefusalReason,
    PrivacyRefused,
    gate_fault_packet,
)
from evorthon_data.verification.enforcement.validation import inspect_verification_record
from evorthon_data.verification.workflows import adviser as workflow
from evorthon_data.verification.workflows.adviser import (
    ADVICE_VERSION,
    ADVISER_REPLY_FORM,
    ADVISER_ROUTE,
    AdviserHypothesis,
    AdviserRefusalReason,
    AdviserRefused,
    AdviserReply,
    AdviserRoute,
    CONTRADICTING_IDENTITIES_FIELD,
    DiagnosticAdviceOutcome,
    SUPPORTING_IDENTITIES_FIELD,
    advise_on_fault,
    adviser_call_fields,
    build_adviser_call,
    read_adviser_reply,
)

NOW = datetime(2026, 9, 9, 9, 0, tzinfo=timezone.utc)
ENGAGEMENT_ID = "engagement-diagnosis"
CASE_ID = "case-daily-output"
IDENTITY_SERVICE = "model-egress-service"
DESTINATION = ModelDestination(
    provider="approved-provider",
    endpoint="models.example.test/v1/respond",
    model="approved-model",
)
AUTHORITY = Identity(
    identifier="data-platform-acceptance-authority",
    version="v1",
    digest=canonical_digest(b"data-platform-acceptance-authority"),
)
CAUSE = "the candidate run left out the population the frozen input declares for the reported grain"
FIX = "restore the declared population filter in the transformation that builds the output"
TEST = "a regression test that counts the declared population at the reported grain and fails when one is absent"
SECOND_CAUSE = "the declared context the run read was not the context the case froze"
SECOND_FIX = "pin the declared context to the frozen one before the run reads it"
SECOND_TEST = "a regression test that compares the declared context identity against the frozen one"
ASSUMPTION = "the declared evidence is synthetic and the localisation is not confirmed"


def route(mode: ModelEgressMode = ModelEgressMode.FAKE) -> AdviserRoute:
    return AdviserRoute(
        destination=DESTINATION,
        mode=mode,
        data_class="bounded-fault-packet",
        retention_policy="environment-30-days",
        evidence_policy="authorization-receipt-only",
    )


class Recorder:
    """Every transport a gateway can reach, and what each one was given."""

    def __init__(self, answer: object = None) -> None:
        self.answer = answer
        self.local: list[ModelCall] = []
        self.fake: list[ModelCall] = []
        self.external: list[ModelCall] = []

    @property
    def sent(self) -> list[ModelCall]:
        return self.local + self.fake + self.external

    def local_transport(self, request: ModelCall) -> object:
        self.local.append(request)
        return self.answer

    def fake_transport(self, request: ModelCall) -> object:
        self.fake.append(request)
        return self.answer

    def external_transport(self, request: ModelCall) -> object:
        self.external.append(request)
        return self.answer


class StaticValidator:
    def __init__(self, status: AuthorizationValidation) -> None:
        self.status = status

    def validate(self, authorization: ModelEgressAuthorization, *, at: datetime) -> AuthorizationValidation:
        return self.status


def status(**changes: object) -> AuthorizationValidation:
    values: dict[str, object] = {
        "authorization_id": "authorization-diagnosis",
        "authenticated_identity": IDENTITY_SERVICE,
        "valid": True,
        "revoked": False,
        "checked_at": NOW,
    }
    values.update(changes)
    return AuthorizationValidation(**values)  # type: ignore[arg-type]


def port(answer: object = None, *, validation: AuthorizationValidation | None = None):
    recorder = Recorder(answer)
    gateway = ModelEgressGateway(
        local_transport=recorder.local_transport,
        fake_transport=recorder.fake_transport,
        external_transport=recorder.external_transport,
        authorization_validator=StaticValidator(validation or status()),
        clock=lambda: NOW,
    )
    return gateway, recorder


def packet() -> GatedFaultPacket:
    """A bounded packet the disclosure policy discloses."""
    return gate_fault_packet(gate_fixture.disclosing_packet())


REPEAT_EVIDENCE_ID = "parity/repeat-observed"


def two_sided_packet() -> GatedFaultPacket:
    """A disclosing packet whose two sides carry distinct evidence identities.

    The declared fixtures happen to name the same evidence on both sides, which
    would let one identity stand for both. The contradicting side is given its
    own identity here so the two identity fields and the two citation sides are
    read independently. The packet still passes the real gate.
    """
    record = build_fault_packet(packets.replay_context_drift())
    declared = record.contradicting_evidence[0]
    distinct = EvidenceReference(
        evidence_id=REPEAT_EVIDENCE_ID,
        version=declared.version,
        digest=packets.fingerprint(REPEAT_EVIDENCE_ID),
        summary=declared.summary,
    )
    return gate_fault_packet(replace(record, contradicting_evidence=(distinct,)))


def withheld_record():
    """A packet the small-cell policy withheld, which the gate never passes."""
    return build_fault_packet(packets.missing_population())


def supporting_id(gated: GatedFaultPacket) -> str:
    return gated.record.supporting_evidence[0].evidence_id


def contradicting_id(gated: GatedFaultPacket) -> str:
    return gated.record.contradicting_evidence[0].evidence_id


def hypothesis(gated: GatedFaultPacket, **changes: object) -> AdviserHypothesis:
    values: dict[str, object] = {
        "cause": CAUSE,
        "proposed_fix": FIX,
        "discriminating_test": TEST,
        "supporting_evidence_ids": (supporting_id(gated),),
        "contradicting_evidence_ids": (),
    }
    values.update(changes)
    return AdviserHypothesis(**values)  # type: ignore[arg-type]


def reply(gated: GatedFaultPacket, **changes: object) -> AdviserReply:
    values: dict[str, object] = {
        "form": ADVISER_REPLY_FORM,
        "confidence": AdviserConfidence.MEDIUM,
        "hypotheses": (hypothesis(gated),),
        "assumptions": (ASSUMPTION,),
    }
    values.update(changes)
    return AdviserReply(**values)  # type: ignore[arg-type]


def unknown_reply() -> AdviserReply:
    return AdviserReply(form=ADVISER_REPLY_FORM, confidence=AdviserConfidence.UNKNOWN)


def run(gated: GatedFaultPacket, answer: object, **changes: object):
    """Run one adviser round through a fake-mode port and return what it saw."""
    values: dict[str, object] = {"route": route(), "authorization": None}
    values.update(changes)
    gateway, recorder = port(answer)
    outcome = advise_on_fault(
        gated,
        engagement_id=ENGAGEMENT_ID,
        case_id=CASE_ID,
        egress=gateway,
        required_authority=AUTHORITY,
        **values,  # type: ignore[arg-type]
    )
    return outcome, recorder


def refusal(gated: GatedFaultPacket, answer: object) -> AdviserRefusalReason:
    with pytest.raises(AdviserRefused) as raised:
        run(gated, answer)
    return raised.value.reason


# --- What crosses the port ---


def test_the_call_carries_the_packets_declared_text_and_its_evidence_identities():
    gated = two_sided_packet()
    call = build_adviser_call(gated, engagement_id=ENGAGEMENT_ID, case_id=CASE_ID, route=route())
    declared = packet_fields(gated.record)

    assert call.purpose is ModelCallPurpose.ADVISER
    assert call.route == ADVISER_ROUTE
    assert dict(declared).items() <= dict(call.fields).items()
    assert call.field_inventory == frozenset(declared) | {
        SUPPORTING_IDENTITIES_FIELD,
        CONTRADICTING_IDENTITIES_FIELD,
    }
    assert call.fields[SUPPORTING_IDENTITIES_FIELD] == (supporting_id(gated),)
    assert call.fields[CONTRADICTING_IDENTITIES_FIELD] == (contradicting_id(gated),)
    assert supporting_id(gated) != contradicting_id(gated)


def test_nothing_beyond_the_packets_own_declarations_crosses_the_port():
    gated = two_sided_packet()
    call = build_adviser_call(gated, engagement_id=ENGAGEMENT_ID, case_id=CASE_ID, route=route())
    declared = set(packet_fields(gated.record).values())
    declared.update(item.evidence_id for item in gated.record.supporting_evidence)
    declared.update(item.evidence_id for item in gated.record.contradicting_evidence)

    for value in call.fields.values():
        for item in (value,) if isinstance(value, str) else value:
            assert item in declared, item


def test_the_call_carries_no_tool_or_callback_surface():
    gated = two_sided_packet()
    call = build_adviser_call(gated, engagement_id=ENGAGEMENT_ID, case_id=CASE_ID, route=route())

    for value in call.fields.values():
        assert not callable(value)
        assert isinstance(value, (str, tuple))
        for item in (value,) if isinstance(value, str) else value:
            assert isinstance(item, str)
            assert not callable(item)


def test_the_adviser_module_declares_no_callable_seam():
    source = Path(workflow.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Lambda)]
    assert "Callable" not in source
    parameters = introspection.signature(advise_on_fault).parameters
    assert set(parameters) == {
        "packet",
        "engagement_id",
        "case_id",
        "route",
        "egress",
        "required_authority",
        "authorization",
    }
    declared_defaults = [
        item.default for item in parameters.values() if item.default is not introspection.Parameter.empty
    ]
    assert declared_defaults == [None]
    assert [value for value in declared_defaults if callable(value)] == []


# --- What comes back ---


def test_a_gated_packet_produces_inert_advice_from_the_declared_reply():
    gated = packet()
    outcome, recorder = run(gated, reply(gated))
    advice = outcome.advice

    assert isinstance(outcome, DiagnosticAdviceOutcome)
    assert isinstance(advice, RemediationAdvice)
    assert len(recorder.fake) == 1 and recorder.external == [] and recorder.local == []
    assert advice.advice_id == f"{gated.record.fault_id}/advice"
    assert advice.version == ADVICE_VERSION
    assert advice.fault == Identity(gated.record.fault_id, gated.record.version, record_digest(gated.record))
    assert advice.hypotheses == (CAUSE,)
    assert advice.proposed_fixes == (FIX,)
    assert advice.discriminating_tests == (
        Identity(TEST, ADVICE_VERSION, canonical_digest(TEST.encode("utf-8"))),
    )
    assert advice.supporting_evidence == (gated.record.supporting_evidence[0],)
    assert advice.contradicting_evidence == ()
    assert advice.assumptions == (ASSUMPTION,)
    assert advice.required_authority == AUTHORITY
    assert advice.confidence is AdviserConfidence.MEDIUM
    assert outcome.confidence is AdviserConfidence.MEDIUM
    assert outcome.is_unknown is False


def test_the_recorded_advice_satisfies_the_products_own_record_validation():
    gated = packet()
    outcome, _ = run(gated, reply(gated))

    assert inspect_verification_record(outcome.advice).issues == ()


def test_more_than_one_hypothesis_is_recorded_in_the_order_it_was_declared():
    gated = two_sided_packet()
    second = hypothesis(
        gated,
        cause=SECOND_CAUSE,
        proposed_fix=SECOND_FIX,
        discriminating_test=SECOND_TEST,
        contradicting_evidence_ids=(contradicting_id(gated),),
    )
    outcome, _ = run(
        gated,
        reply(gated, hypotheses=(hypothesis(gated), second), confidence=AdviserConfidence.HIGH),
    )
    advice = outcome.advice

    assert advice.hypotheses == (CAUSE, SECOND_CAUSE)
    assert advice.proposed_fixes == (FIX, SECOND_FIX)
    assert tuple(item.identifier for item in advice.discriminating_tests) == (TEST, SECOND_TEST)
    assert advice.supporting_evidence == (gated.record.supporting_evidence[0],)
    assert advice.contradicting_evidence == (gated.record.contradicting_evidence[0],)
    assert inspect_verification_record(advice).issues == ()


def test_an_unknown_answer_is_a_real_answer_and_records_no_advice():
    gated = packet()
    outcome, recorder = run(gated, unknown_reply())

    assert len(recorder.fake) == 1
    assert outcome.advice is None
    assert outcome.is_unknown is True
    assert outcome.confidence is AdviserConfidence.UNKNOWN


def test_weak_or_synthetic_evidence_lowers_confidence_and_never_withholds():
    gated = packet()
    lowered, _ = run(gated, reply(gated, confidence=AdviserConfidence.LOW))
    raised, _ = run(gated, reply(gated, confidence=AdviserConfidence.HIGH))

    assert gated.record.localisation.status.value == "unknown"
    assert lowered.advice.confidence is AdviserConfidence.LOW
    assert raised.advice.confidence is AdviserConfidence.HIGH
    assert lowered.advice.assumptions == (ASSUMPTION,)


# --- The authority: every failure sends nothing ---


def authorization(call: ModelCall, **changes: object) -> ModelEgressAuthorization:
    values: dict[str, object] = {
        "authorization_id": "authorization-diagnosis",
        "engagement_id": call.engagement_id,
        "case_id": call.case_id,
        "purpose": call.purpose,
        "route": call.route,
        "destination": call.destination,
        "permitted_fields": call.field_inventory,
        "data_class": call.data_class,
        "retention_policy": call.retention_policy,
        "evidence_policy": call.evidence_policy,
        "expected_authenticated_identity": IDENTITY_SERVICE,
        "not_before": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(minutes=1),
    }
    values.update(changes)
    return ModelEgressAuthorization(**values)  # type: ignore[arg-type]


def external_call(gated: GatedFaultPacket) -> ModelCall:
    return build_adviser_call(
        gated, engagement_id=ENGAGEMENT_ID, case_id=CASE_ID, route=route(ModelEgressMode.EXTERNAL)
    )


def test_an_external_call_under_a_current_scoped_authority_reaches_one_transport():
    gated = packet()
    outcome, recorder = run(
        gated,
        reply(gated),
        route=route(ModelEgressMode.EXTERNAL),
        authorization=authorization(external_call(gated)),
    )

    assert len(recorder.external) == 1 and recorder.fake == [] and recorder.local == []
    assert outcome.advice.confidence is AdviserConfidence.MEDIUM


AUTHORITY_FAILURES = (
    ("a missing authority", None, None, EgressDenialReason.AUTHORIZATION_REQUIRED),
    (
        "an invalid authority",
        {},
        {"valid": False},
        EgressDenialReason.VALIDATION_FAILED,
    ),
    (
        "an expired authority",
        {"not_before": NOW - timedelta(minutes=5), "expires_at": NOW - timedelta(minutes=1)},
        None,
        EgressDenialReason.AUTHORIZATION_EXPIRED,
    ),
    (
        "a revoked authority",
        {},
        {"revoked": True},
        EgressDenialReason.AUTHORIZATION_REVOKED,
    ),
    (
        "a policy-mismatched authority",
        {"retention_policy": "environment-indefinite"},
        None,
        EgressDenialReason.SCOPE_MISMATCH,
    ),
    (
        "an authority scoped to other fields",
        {"permitted_fields": frozenset({"fault_id"})},
        None,
        EgressDenialReason.SCOPE_MISMATCH,
    ),
    (
        "an authority for another identity",
        {},
        {"authenticated_identity": "another-service"},
        EgressDenialReason.AUTHENTICATION_MISMATCH,
    ),
)


@pytest.mark.parametrize(
    ("scope_changes", "status_changes", "expected"),
    [(scope, state, expected) for _, scope, state, expected in AUTHORITY_FAILURES],
    ids=[name for name, _, _, _ in AUTHORITY_FAILURES],
)
def test_an_authority_failure_sends_nothing(scope_changes, status_changes, expected):
    gated = packet()
    gateway, recorder = port(reply(gated), validation=status(**(status_changes or {})))
    granted = None if scope_changes is None else authorization(external_call(gated), **scope_changes)

    with pytest.raises(ModelEgressDenied) as raised:
        advise_on_fault(
            gated,
            engagement_id=ENGAGEMENT_ID,
            case_id=CASE_ID,
            route=route(ModelEgressMode.EXTERNAL),
            egress=gateway,
            required_authority=AUTHORITY,
            authorization=granted,
        )

    assert raised.value.reason is expected
    assert recorder.sent == []


# --- The gate: a packet that did not pass it sends nothing ---


def test_a_raw_fault_record_sends_nothing():
    gateway, recorder = port(None)

    with pytest.raises(AdviserRefused) as raised:
        advise_on_fault(
            gate_fixture.disclosing_packet(),
            engagement_id=ENGAGEMENT_ID,
            case_id=CASE_ID,
            route=route(),
            egress=gateway,
            required_authority=AUTHORITY,
        )

    assert raised.value.reason is AdviserRefusalReason.UNGATED_PACKET
    assert recorder.sent == []


def test_a_packet_declaring_another_gate_sends_nothing():
    gateway, recorder = port(None)
    forged = replace(packet(), gate="other.gate.v1")

    with pytest.raises(AdviserRefused) as raised:
        advise_on_fault(
            forged,
            engagement_id=ENGAGEMENT_ID,
            case_id=CASE_ID,
            route=route(),
            egress=gateway,
            required_authority=AUTHORITY,
        )

    assert raised.value.reason is AdviserRefusalReason.UNGATED_PACKET
    assert recorder.sent == []


def test_a_withheld_small_cell_packet_assembled_by_hand_sends_nothing():
    record = withheld_record()
    gateway, recorder = port(None)
    forged = GatedFaultPacket(record=record, bounds=PACKET_BOUNDS)

    assert record.disclosure_decision is DisclosureDecision.WITHHOLD_SMALL_CELL
    with pytest.raises(PrivacyRefused) as raised:
        advise_on_fault(
            forged,
            engagement_id=ENGAGEMENT_ID,
            case_id=CASE_ID,
            route=route(),
            egress=gateway,
            required_authority=AUTHORITY,
        )

    assert raised.value.reason is PrivacyRefusalReason.DISCLOSURE_WITHHELD
    assert recorder.sent == []


# --- The bounds are the product's, not the packet's own declaration ---


RELAXED_BOUNDS = tuple(PACKET_BOUNDS.__dataclass_fields__)


@pytest.mark.parametrize("measure", RELAXED_BOUNDS, ids=RELAXED_BOUNDS)
def test_a_packet_declaring_a_looser_bound_than_the_product_sends_nothing(measure):
    gateway, recorder = port(None)
    relaxed = replace(PACKET_BOUNDS, **{measure: getattr(PACKET_BOUNDS, measure) + 1})
    forged = replace(packet(), bounds=relaxed)

    with pytest.raises(AdviserRefused) as raised:
        advise_on_fault(
            forged,
            engagement_id=ENGAGEMENT_ID,
            case_id=CASE_ID,
            route=route(),
            egress=gateway,
            required_authority=AUTHORITY,
        )

    assert raised.value.reason is AdviserRefusalReason.RELAXED_BOUNDS
    assert raised.value.subject == f"packet.bounds.{measure}"
    assert recorder.sent == []


def test_an_over_long_scope_cannot_ride_in_on_a_packet_s_own_relaxed_bounds():
    """A packet assembled by hand: relaxed bounds carrying an over-long scope."""
    gateway, recorder = port(None)
    over_long = replace(
        gate_fixture.disclosing_packet(),
        diagnostic_scope="output daily-output; " + "scope " * (PACKET_BOUNDS.text_characters // 2),
    )
    forged = GatedFaultPacket(
        record=over_long, bounds=replace(PACKET_BOUNDS, text_characters=4096)
    )

    assert len(over_long.diagnostic_scope) > PACKET_BOUNDS.text_characters
    with pytest.raises(AdviserRefused) as raised:
        advise_on_fault(
            forged,
            engagement_id=ENGAGEMENT_ID,
            case_id=CASE_ID,
            route=route(),
            egress=gateway,
            required_authority=AUTHORITY,
        )

    assert raised.value.reason is AdviserRefusalReason.RELAXED_BOUNDS
    assert recorder.sent == []


def test_a_packet_declaring_the_product_s_own_bounds_still_crosses():
    gated = replace(packet(), bounds=PACKET_BOUNDS)
    outcome, recorder = run(gated, reply(gated))

    assert len(recorder.sent) == 1
    assert recorder.sent[0].route == ADVISER_ROUTE
    assert outcome.advice is not None
    assert outcome.confidence is AdviserConfidence.MEDIUM


def test_a_packet_declaring_no_bounds_at_all_sends_nothing():
    gateway, recorder = port(None)
    forged = replace(packet(), bounds="every bound this packet likes")

    with pytest.raises(AdviserRefused) as raised:
        advise_on_fault(
            forged,
            engagement_id=ENGAGEMENT_ID,
            case_id=CASE_ID,
            route=route(),
            egress=gateway,
            required_authority=AUTHORITY,
        )

    assert raised.value.reason is AdviserRefusalReason.RELAXED_BOUNDS
    assert raised.value.subject == "packet.bounds"
    assert recorder.sent == []


# --- The reply is recorded as it was written, and nothing carries it out ---


SHELL_LINE = "$ pytest tests/verification -k population"
FENCED_BLOCK = "```sql\nselect count(*) from daily_output\n```"
UPDATE_STATEMENT = "update the rows so the declared population is present"
TOLERANCE_TEXT = "change the tolerance to two decimal places"
TRACKER_TEXT = "mark the item done"
ACCEPTANCE_TEXT = "accept the version"
CARRIED_TEXTS = (SHELL_LINE, FENCED_BLOCK, UPDATE_STATEMENT, TOLERANCE_TEXT, TRACKER_TEXT, ACCEPTANCE_TEXT)


def carrying_reply(gated: GatedFaultPacket) -> AdviserReply:
    """A reply whose every declared text is something a filter would have caught."""
    first = hypothesis(gated, cause=SHELL_LINE, proposed_fix=FENCED_BLOCK, discriminating_test=UPDATE_STATEMENT)
    second = hypothesis(
        gated, cause=TOLERANCE_TEXT, proposed_fix=TRACKER_TEXT, discriminating_test=ACCEPTANCE_TEXT
    )
    return reply(gated, hypotheses=(first, second))


def test_a_reply_carrying_commands_and_actions_is_recorded_exactly_as_text():
    gated = packet()
    outcome, _ = run(gated, carrying_reply(gated))
    advice = outcome.advice

    assert advice.hypotheses == (SHELL_LINE, TOLERANCE_TEXT)
    assert advice.proposed_fixes == (FENCED_BLOCK, TRACKER_TEXT)
    assert tuple(item.identifier for item in advice.discriminating_tests) == (UPDATE_STATEMENT, ACCEPTANCE_TEXT)
    recorded = (*advice.hypotheses, *advice.proposed_fixes, *(item.identifier for item in advice.discriminating_tests))
    for written in CARRIED_TEXTS:
        assert written.encode("utf-8") in [item.encode("utf-8") for item in recorded]
    assert inspect_verification_record(advice).issues == ()


def test_the_advice_record_carries_plain_text_and_nothing_callable():
    gated = packet()
    outcome, _ = run(gated, carrying_reply(gated))

    for name, value in vars(outcome.advice).items():
        for leaf in flattened(value):
            assert isinstance(leaf, (str, Enum)), (name, leaf)
            assert not callable(leaf), (name, leaf)


def flattened(value: object):
    """Yield every leaf of a declared record, refusing anything that is not one."""
    if isinstance(value, (str, Enum)):
        yield value
    elif isinstance(value, tuple):
        for item in value:
            yield from flattened(item)
    elif is_dataclass(value):
        for item in vars(value).values():
            yield from flattened(item)
    else:
        yield value


class Sentinels:
    """Every way out of this process, watched for exactly one adviser round.

    The replacements are installed around the call and taken off again in a
    finally, rather than for the length of a test, because the interpreter's
    own machinery uses several of these names and a watcher left standing
    would be answering for work that is not the round.
    """

    WATCHED = (
        (subprocess, "run", "subprocess.run"),
        (subprocess, "Popen", "subprocess.Popen"),
        (subprocess, "call", "subprocess.call"),
        (subprocess, "check_output", "subprocess.check_output"),
        (os, "system", "os.system"),
        (os, "popen", "os.popen"),
        (builtins, "eval", "eval"),
        (builtins, "exec", "exec"),
        (builtins, "compile", "compile"),
        (importlib, "import_module", "importlib.import_module"),
        (runpy, "run_path", "runpy.run_path"),
    )

    def __init__(self) -> None:
        self.taken: list[str] = []
        self._restore: list[tuple[object, str, object]] = []

    def _trip(self, name: str):
        def taken(*args: object, **kwargs: object):
            self.taken.append(name)
            raise AssertionError(f"the adviser round reached {name}")

        return taken

    def _watched_open(self, original):
        def opened(file, mode="r", *args: object, **kwargs: object):
            if any(flag in str(mode) for flag in ("w", "a", "x", "+")):
                self.taken.append("open for writing")
                raise AssertionError("the adviser round opened a file for writing")
            return original(file, mode, *args, **kwargs)

        return opened

    def _watched_import(self, original):
        def imported(name, *args: object, **kwargs: object):
            self.taken.append(f"import {name}")
            return original(name, *args, **kwargs)

        return imported

    def __enter__(self) -> "Sentinels":
        for holder, attribute, name in self.WATCHED:
            self._restore.append((holder, attribute, getattr(holder, attribute)))
            setattr(holder, attribute, self._trip(name))
        for attribute, wrap in (("open", self._watched_open), ("__import__", self._watched_import)):
            original = getattr(builtins, attribute)
            self._restore.append((builtins, attribute, original))
            setattr(builtins, attribute, wrap(original))
        return self

    def __exit__(self, *details: object) -> None:
        for holder, attribute, original in reversed(self._restore):
            setattr(holder, attribute, original)
        self._restore.clear()


def test_no_execution_path_is_taken_while_a_carrying_reply_is_recorded():
    gated = packet()
    answer = carrying_reply(gated)
    gateway, recorder = port(answer)
    sentinels = Sentinels()

    with sentinels:
        outcome = advise_on_fault(
            gated,
            engagement_id=ENGAGEMENT_ID,
            case_id=CASE_ID,
            route=route(),
            egress=gateway,
            required_authority=AUTHORITY,
        )

    assert sentinels.taken == []
    assert len(recorder.fake) == 1
    assert outcome.advice.hypotheses == (SHELL_LINE, TOLERANCE_TEXT)
    assert outcome.advice.proposed_fixes == (FENCED_BLOCK, TRACKER_TEXT)


# The composition root asks the adviser workflow for a round and reads the
# advice document a later route is given. The records it writes are the facts a
# workflow decided; the one advice it writes is the record the adviser workflow
# made, serialized verbatim and changed in no way. The rule below would
# otherwise forbid the root every record it legitimately writes, so the root is
# named here and held to the two rules beside it instead.
ADVICE_ROUTE = Path(__file__).parents[2] / "src/evorthon_data/composition.py"
# Every other product module that reads the advice record. The advice must not
# reach an interpreter, a process, a file or another model call in any of them.
ADVICE_READERS = tuple(
    path
    for path in sorted((Path(__file__).parents[2] / "src/evorthon_data").rglob("*.py"))
    if "RemediationAdvice" in path.read_text(encoding="utf-8") and path != ADVICE_ROUTE
)
FORBIDDEN_CALLS = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "os.system",
        "os.popen",
        "os.execv",
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_output",
        "runpy.run_path",
        "runpy.run_module",
        "importlib.import_module",
    }
)
FORBIDDEN_MODULES = frozenset({"subprocess", "runpy", "importlib", "shutil", "socket"})


def dotted(node: ast.AST) -> str:
    """Return the written name of a call target, so that re.compile is not compile."""
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def called_names(tree: ast.AST) -> set[str]:
    return {dotted(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def imported_paths(tree: ast.AST) -> set[str]:
    paths: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            paths.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            paths.update(f"{node.module}.{alias.name}" for alias in node.names)
    return paths


def imported_names(tree: ast.AST) -> set[str]:
    return {path.partition(".")[0] for path in imported_paths(tree)}


def writing_opens(tree: ast.AST) -> list[str]:
    opened: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if name not in {"open", "write_text", "write_bytes", "mkdir", "touch", "unlink"}:
            continue
        if name != "open":
            opened.append(name)
            continue
        modes = [item.value for item in node.args[1:2] if isinstance(item, ast.Constant)]
        modes += [item.value.value for item in node.keywords if item.arg == "mode" and isinstance(item.value, ast.Constant)]
        if any(flag in str(mode) for mode in modes for flag in ("w", "a", "x", "+")):
            opened.append(name)
    return opened


EXPORTING_MODULES = ("evorthon_data.verification.workflows.adviser", "evorthon_data.verification.workflows")


@pytest.mark.parametrize("module_name", EXPORTING_MODULES)
def test_every_exported_name_resolves_under_a_star_import(module_name):
    """A name left in an export list after its owner is deleted breaks a star import."""
    module = importlib.import_module(module_name)
    declared = list(module.__all__)
    imported: dict[str, object] = {}

    exec(f"from {module_name} import *", imported)

    assert declared == sorted(declared), module_name
    assert len(declared) == len(set(declared)), module_name
    assert [name for name in declared if not hasattr(module, name)] == []
    assert [name for name in declared if name not in imported] == []


def test_at_least_the_adviser_and_the_validator_are_among_the_advice_readers():
    names = {path.name for path in ADVICE_READERS}

    assert {"adviser.py", "validation.py", "contracts.py"} <= names


@pytest.mark.parametrize("path", ADVICE_READERS, ids=[path.name for path in ADVICE_READERS])
def test_no_module_that_reads_the_advice_can_run_or_write_anything(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))

    assert called_names(tree) & FORBIDDEN_CALLS == set()
    assert imported_names(tree) & FORBIDDEN_MODULES == set()
    assert writing_opens(tree) == []


def test_the_only_model_call_in_the_adviser_is_built_from_the_gated_packet():
    tree = ast.parse(Path(workflow.__file__).read_text(encoding="utf-8"))
    constructions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ModelCall"
    ]

    assert len(constructions) == 1
    fields = [item.value for item in constructions[0].keywords if item.arg == "fields"]
    assert len(fields) == 1
    assert isinstance(fields[0], ast.Call)
    assert getattr(fields[0].func, "id", "") == "adviser_call_fields"


TRACKER_ROUTES = (Path(__file__).parents[2] / "src/evorthon_data/delivery/pinax.py",)
# The advice a person disposed of never reaches the tracker: the adapter reads
# the decision and the work it approved, and nothing of what was advised.


@pytest.mark.parametrize("path", TRACKER_ROUTES, ids=[path.name for path in TRACKER_ROUTES])
def test_the_tracker_adapter_never_reads_the_advice(path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert path not in ADVICE_READERS
    for name in ("RemediationAdvice", "DiagnosticAdviceOutcome", "advise_on_fault", "read_adviser_reply"):
        assert name not in source, name
    assert [item for item in imported_paths(tree) if "adviser" in item or "advice" in item] == []


@pytest.mark.parametrize("module_name", ["evorthon_data.delivery.pinax"])
def test_the_tracker_adapter_holds_no_advice_symbol(module_name):
    module = importlib.import_module(module_name)

    assert not [name for name, value in vars(module).items() if value is RemediationAdvice]
    assert not [name for name in vars(module) if "advice" in name.lower() or "adviser" in name.lower()]


def test_the_composition_root_runs_no_advice_and_reads_no_reply():
    """The one route that asks for advice never runs it and never reads a reply.

    The root asks the adviser workflow for a round, because a supported
    application route has to reach the adviser somewhere and the root is the
    one component the architecture lets reach it. What it may never do is read
    a reply itself, name the outcome type the workflow answers with, or reach
    an interpreter, a process or another model call with what came back. The
    reply is read by the workflow that owns the reader, so nothing in the root
    decides what a reply supports.
    """
    source = ADVICE_ROUTE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "RemediationAdvice" in source
    for name in ("DiagnosticAdviceOutcome", "read_adviser_reply"):
        assert name not in source, name
    assert called_names(tree) & FORBIDDEN_CALLS == set()
    assert imported_names(tree) & FORBIDDEN_MODULES == set()
    assert [item for item in imported_paths(tree) if "adviser" in item] == []


ADVICE_WRITES = frozenset({"write_text", "write_bytes", "writelines", "write"})
# One further write of the advice, injected to drive the rule below red.
SECOND_ADVICE_WRITE = (
    "def _injected(place, advice):\n"
    "    return place.write_text(str(advice), encoding='ascii')\n"
)


def advice_writes(tree: ast.AST) -> list[ast.AST]:
    """Every argument one source hands to a file write that carries the advice."""
    written: list[ast.AST] = []
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr not in ADVICE_WRITES
            or not node.args
        ):
            continue
        carried = node.args[0]
        names = {item.id for item in ast.walk(carried) if isinstance(item, ast.Name)}
        names |= {item.attr for item in ast.walk(carried) if isinstance(item, ast.Attribute)}
        if "advice" in names:
            written.append(carried)
    return written


def test_the_only_advice_the_composition_root_writes_is_the_workflow_s_own_record():
    """The advice reaches a document as the serializer wrote it, and no other way."""
    tree = ast.parse(ADVICE_ROUTE.read_text(encoding="utf-8"))
    carried = advice_writes(tree)
    serializations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func) == "serialize_json"
    ]

    assert len(carried) == 1
    written = carried[0]
    assert isinstance(written, ast.Call)
    assert dotted(written.func) == "serialize_json"
    assert [dotted(argument) for argument in written.args] == ["advice"]
    assert written.keywords == []
    # The serializer is reached once, for that one write, so nothing else in
    # the root turns a piece of advice into text a document holds.
    assert serializations == [written]


def test_a_second_advice_write_in_the_composition_root_reddens_the_rule():
    clean = ADVICE_ROUTE.read_text(encoding="utf-8")
    injected = advice_writes(ast.parse(clean + "\n\n" + SECOND_ADVICE_WRITE))

    assert len(advice_writes(ast.parse(clean))) == 1
    assert len(injected) == 2
    assert [dotted(item.func) for item in injected if isinstance(item, ast.Call)] != [
        "serialize_json"
    ]


def test_a_citation_the_packet_does_not_carry_is_refused():
    gated = packet()
    invented = hypothesis(gated, supporting_evidence_ids=("evidence-nobody-declared",))

    assert refusal(gated, reply(gated, hypotheses=(invented,))) is AdviserRefusalReason.UNCITED_EVIDENCE


def test_a_citation_on_the_wrong_side_of_the_argument_is_refused():
    gated = two_sided_packet()
    crossed = hypothesis(gated, contradicting_evidence_ids=(supporting_id(gated),))

    assert supporting_id(gated) not in {item.evidence_id for item in gated.record.contradicting_evidence}
    assert refusal(gated, reply(gated, hypotheses=(crossed,))) is AdviserRefusalReason.UNCITED_EVIDENCE


def test_a_hypothesis_resting_on_no_evidence_is_refused():
    gated = packet()
    unsupported = hypothesis(gated, supporting_evidence_ids=())

    assert refusal(gated, reply(gated, hypotheses=(unsupported,))) is AdviserRefusalReason.INCOMPLETE_HYPOTHESIS


@pytest.mark.parametrize("field", ["cause", "proposed_fix", "discriminating_test"])
def test_a_hypothesis_missing_a_declaration_is_refused(field):
    gated = packet()
    incomplete = hypothesis(gated, **{field: "   "})

    assert refusal(gated, reply(gated, hypotheses=(incomplete,))) is AdviserRefusalReason.INCOMPLETE_HYPOTHESIS


def test_a_declaration_made_twice_is_refused():
    gated = packet()
    repeated = (hypothesis(gated), hypothesis(gated, proposed_fix=SECOND_FIX, discriminating_test=SECOND_TEST))

    assert refusal(gated, reply(gated, hypotheses=repeated)) is AdviserRefusalReason.REPEATED_DECLARATION


def test_a_repeated_assumption_is_refused():
    gated = packet()

    assert refusal(gated, reply(gated, assumptions=(ASSUMPTION, ASSUMPTION))) is AdviserRefusalReason.REPEATED_DECLARATION


UNRESOLVED_REPLIES = (
    ("free text", "the cause is probably the population filter"),
    ("another declared form", AdviserReply(form="other.reply.v1", confidence=AdviserConfidence.UNKNOWN)),
    ("nothing at all", None),
)


@pytest.mark.parametrize(
    "answer",
    [answer for _, answer in UNRESOLVED_REPLIES],
    ids=[name for name, _ in UNRESOLVED_REPLIES],
)
def test_a_reply_outside_the_declared_form_is_refused(answer):
    assert refusal(packet(), answer) is AdviserRefusalReason.UNRESOLVED_REPLY


def test_hypotheses_declared_with_an_unknown_confidence_are_refused():
    gated = packet()

    assert refusal(gated, reply(gated, confidence=AdviserConfidence.UNKNOWN)) is AdviserRefusalReason.CONTRADICTORY_REPLY


def test_an_answer_with_no_hypothesis_and_a_stated_confidence_is_refused():
    gated = packet()
    empty = reply(gated, hypotheses=(), confidence=AdviserConfidence.HIGH)

    assert refusal(gated, empty) is AdviserRefusalReason.CONTRADICTORY_REPLY


def test_a_refused_reply_records_no_advice_at_all():
    gated = packet()
    uncited = reply(gated, hypotheses=(hypothesis(gated, supporting_evidence_ids=("evidence-nobody-declared",)),))

    with pytest.raises(AdviserRefused) as raised:
        read_adviser_reply(uncited, gated, required_authority=AUTHORITY)

    assert raised.value.reason is AdviserRefusalReason.UNCITED_EVIDENCE


def test_reading_a_reply_against_an_ungated_packet_is_refused():
    gated = packet()

    with pytest.raises(AdviserRefused) as raised:
        read_adviser_reply(reply(gated), gated.record, required_authority=AUTHORITY)

    assert raised.value.reason is AdviserRefusalReason.UNGATED_PACKET


# --- The prompt the adviser answers from states the same contract ---


ADVISER_PROMPT = Path(__file__).parents[2] / "koine/prompts/generators/advise-on-fault.md"
ADVISER_REVIEWER_PROMPT = Path(__file__).parents[2] / "koine/prompts/reviewers/advise-on-fault-reviewer.md"
DECLARED_REPLY_PARTS = (
    "confidence",
    "assumptions",
    "hypotheses",
    "cause",
    "proposed fix",
    "discriminating regression test",
    "supporting evidence",
    "contradicting evidence",
    "unknown",
)
DECLARED_HANDLING = (
    "recorded word for word",
    "nothing in the product runs it",
    "a person reads what you wrote",
    "the packet does not carry",
)


@pytest.mark.parametrize("part", DECLARED_REPLY_PARTS)
def test_the_pack_prompt_states_the_declared_reply_form(part):
    assert part in ADVISER_PROMPT.read_text(encoding="utf-8").lower()


@pytest.mark.parametrize("statement", DECLARED_HANDLING)
def test_the_pack_prompt_states_how_the_product_handles_the_answer(statement):
    assert statement in ADVISER_PROMPT.read_text(encoding="utf-8").lower()


def test_the_pack_reviewer_prompt_reads_register_rather_than_forbidden_words():
    text = ADVISER_REVIEWER_PROMPT.read_text(encoding="utf-8").lower()

    assert "inert text" in text
    assert "runs none of them" in text
    assert "report findings for the human decision" in text
    assert "weak, synthetic or derived evidence lowers confidence without withholding an answer" in text
    assert "use unknown when the packet does not support a cause" in text


def test_the_field_owner_refuses_a_packet_that_did_not_pass_the_gate():
    with pytest.raises(AdviserRefused) as raised:
        adviser_call_fields(gate_fixture.disclosing_packet())

    assert raised.value.reason is AdviserRefusalReason.UNGATED_PACKET
