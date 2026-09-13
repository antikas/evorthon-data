from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

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
    ModelEgressPort,
)


NOW = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
DESTINATION = ModelDestination(
    provider="approved-provider",
    endpoint="https://models.example.test/v1/respond",
    model="approved-model",
)


class Recorder:
    def __init__(self) -> None:
        self.local: list[ModelCall] = []
        self.fake: list[ModelCall] = []
        self.external: list[ModelCall] = []

    def local_transport(self, request: ModelCall) -> str:
        self.local.append(request)
        return "local-result"

    def fake_transport(self, request: ModelCall) -> str:
        self.fake.append(request)
        return "fake-result"

    def external_transport(self, request: ModelCall) -> str:
        self.external.append(request)
        return "external-result"


class StaticValidator:
    def __init__(self, status: AuthorizationValidation) -> None:
        self.status = status
        self.calls: list[ModelEgressAuthorization] = []

    def validate(self, authorization: ModelEgressAuthorization, *, at: datetime) -> AuthorizationValidation:
        self.calls.append(authorization)
        return self.status


def request(**changes: object) -> ModelCall:
    values: dict[str, object] = {
        "engagement_id": "engagement-7",
        "case_id": "case-9",
        "purpose": ModelCallPurpose.GENERATOR,
        "route": "koine.frame.outcome",
        "destination": DESTINATION,
        "fields": {"outcome": "synthetic outcome", "constraints": "synthetic constraints"},
        "data_class": "synthetic-approved-summary",
        "retention_policy": "environment-30-days",
        "evidence_policy": "authorization-receipt-only",
        "mode": ModelEgressMode.EXTERNAL,
    }
    values.update(changes)
    return ModelCall(**values)  # type: ignore[arg-type]


def authorization(**changes: object) -> ModelEgressAuthorization:
    model_request = request()
    values: dict[str, object] = {
        "authorization_id": "authorization-3",
        "engagement_id": model_request.engagement_id,
        "case_id": model_request.case_id,
        "purpose": model_request.purpose,
        "route": model_request.route,
        "destination": model_request.destination,
        "permitted_fields": model_request.field_inventory,
        "data_class": model_request.data_class,
        "retention_policy": model_request.retention_policy,
        "evidence_policy": model_request.evidence_policy,
        "expected_authenticated_identity": "model-egress-service",
        "not_before": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(minutes=1),
    }
    values.update(changes)
    return ModelEgressAuthorization(**values)  # type: ignore[arg-type]


def status(**changes: object) -> AuthorizationValidation:
    values: dict[str, object] = {
        "authorization_id": "authorization-3",
        "authenticated_identity": "model-egress-service",
        "valid": True,
        "revoked": False,
        "checked_at": NOW,
    }
    values.update(changes)
    return AuthorizationValidation(**values)  # type: ignore[arg-type]


def gateway(*, validation: AuthorizationValidation | None = None) -> tuple[ModelEgressGateway, Recorder, StaticValidator]:
    recorder = Recorder()
    validator = StaticValidator(validation or status())
    return (
        ModelEgressGateway(
            local_transport=recorder.local_transport,
            fake_transport=recorder.fake_transport,
            external_transport=recorder.external_transport,
            authorization_validator=validator,
            clock=lambda: NOW,
        ),
        recorder,
        validator,
    )


def assert_denied(
    gateway: ModelEgressGateway,
    recorder: Recorder,
    model_request: ModelCall,
    model_authorization: ModelEgressAuthorization | None,
    reason: EgressDenialReason,
) -> None:
    with pytest.raises(ModelEgressDenied) as raised:
        gateway.invoke(model_request, model_authorization)
    assert raised.value.reason is reason
    assert recorder.external == []


def test_local_and_fake_calls_need_no_external_authorization_or_egress():
    secured_gateway, recorder, validator = gateway()

    assert secured_gateway.invoke(request(mode=ModelEgressMode.LOCAL)) == "local-result"
    assert secured_gateway.invoke(request(mode=ModelEgressMode.FAKE)) == "fake-result"

    assert len(recorder.local) == 1
    assert len(recorder.fake) == 1
    assert recorder.external == []
    assert validator.calls == []


@pytest.mark.parametrize("purpose", list(ModelCallPurpose))
def test_one_gateway_authorizes_each_generator_reviewer_and_adviser_route(purpose: ModelCallPurpose):
    secured_gateway, recorder, validator = gateway()
    scoped_request = request(purpose=purpose)
    scoped_authorization = authorization(purpose=purpose)

    assert secured_gateway.invoke(scoped_request, scoped_authorization) == "external-result"
    assert recorder.external == [scoped_request]
    assert validator.calls == [scoped_authorization]


def test_external_egress_requires_an_explicit_authorization_even_with_ambient_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-value-is-not-product-authority")
    monkeypatch.setenv("MODEL_HARNESS_LOGIN", "ambient-login-is-not-product-authority")
    secured_gateway, recorder, validator = gateway()

    assert_denied(secured_gateway, recorder, request(), None, EgressDenialReason.AUTHORIZATION_REQUIRED)
    assert validator.calls == []


@pytest.mark.parametrize(
    ("request_changes", "authorization_changes"),
    [
        ({"engagement_id": "other-engagement"}, {}),
        ({"case_id": "other-case"}, {}),
        ({"purpose": ModelCallPurpose.REVIEWER}, {}),
        ({"route": "koine.review.outcome"}, {}),
        ({"destination": ModelDestination("other-provider", DESTINATION.endpoint, DESTINATION.model)}, {}),
        ({"destination": ModelDestination(DESTINATION.provider, "https://other.example.test/v1/respond", DESTINATION.model)}, {}),
        ({"destination": ModelDestination(DESTINATION.provider, DESTINATION.endpoint, "other-model")}, {}),
        ({"data_class": "raw-enterprise-data"}, {}),
        ({"retention_policy": "unapproved-retention"}, {}),
        ({"evidence_policy": "unapproved-evidence"}, {}),
        ({"fields": {"outcome": "synthetic outcome", "constraints": "synthetic constraints", "extra": "not-authorized"}}, {}),
        ({"fields": {"outcome": "synthetic outcome"}}, {}),
    ],
    ids=(
        "wrong-engagement",
        "wrong-case",
        "wrong-purpose",
        "wrong-route",
        "wrong-provider",
        "wrong-endpoint",
        "wrong-model",
        "wrong-data-class",
        "wrong-retention-policy",
        "wrong-evidence-policy",
        "field-superset",
        "field-subset",
    ),
)
def test_scope_mismatches_send_nothing(request_changes, authorization_changes):
    secured_gateway, recorder, validator = gateway()
    scoped_request = request(**request_changes)
    scoped_authorization = authorization(**authorization_changes)

    assert_denied(
        secured_gateway,
        recorder,
        scoped_request,
        scoped_authorization,
        EgressDenialReason.SCOPE_MISMATCH,
    )
    assert validator.calls == []


@pytest.mark.parametrize(
    ("authorization_changes", "validation", "reason"),
    [
        (
            {"not_before": NOW - timedelta(minutes=2), "expires_at": NOW},
            status(),
            EgressDenialReason.AUTHORIZATION_EXPIRED,
        ),
        (
            {},
            status(revoked=True),
            EgressDenialReason.AUTHORIZATION_REVOKED,
        ),
        (
            {},
            status(authenticated_identity="other-model-egress-service"),
            EgressDenialReason.AUTHENTICATION_MISMATCH,
        ),
        (
            {},
            status(authenticated_identity=None),
            EgressDenialReason.AUTHENTICATION_REQUIRED,
        ),
        (
            {},
            status(valid=False),
            EgressDenialReason.VALIDATION_FAILED,
        ),
        (
            {},
            status(checked_at=NOW - timedelta(seconds=61)),
            EgressDenialReason.VALIDATION_NOT_CURRENT,
        ),
        (
            {},
            status(authorization_id="other-authorization"),
            EgressDenialReason.VALIDATION_FAILED,
        ),
    ],
    ids=(
        "expired",
        "revoked",
        "authenticated-identity-mismatch",
        "missing-authenticated-identity",
        "invalid-environment-status",
        "stale-environment-status",
        "wrong-environment-authorization",
    ),
)
def test_not_current_or_invalid_environment_authorization_sends_nothing(authorization_changes, validation, reason):
    secured_gateway, recorder, validator = gateway(validation=validation)
    scoped_authorization = authorization(**authorization_changes)

    assert_denied(secured_gateway, recorder, request(), scoped_authorization, reason)
    expected_calls = [] if reason is EgressDenialReason.AUTHORIZATION_EXPIRED else [scoped_authorization]
    assert validator.calls == expected_calls


def test_no_validator_or_external_transport_fails_closed_before_a_send():
    recorder = Recorder()
    no_validator = ModelEgressGateway(
        local_transport=recorder.local_transport,
        external_transport=recorder.external_transport,
        clock=lambda: NOW,
    )
    assert_denied(no_validator, recorder, request(), authorization(), EgressDenialReason.VALIDATION_FAILED)

    no_transport = ModelEgressGateway(
        local_transport=recorder.local_transport,
        authorization_validator=StaticValidator(status()),
        clock=lambda: NOW,
    )
    assert_denied(no_transport, recorder, request(), authorization(), EgressDenialReason.EXTERNAL_TRANSPORT_UNAVAILABLE)


def test_consumers_receive_a_port_without_a_transport_escape_hatch():
    secured_gateway, recorder, _ = gateway()

    assert isinstance(secured_gateway, ModelEgressPort)
    assert tuple(inspect.signature(secured_gateway.invoke).parameters) == ("request", "authorization")
    assert not hasattr(secured_gateway, "external_transport")
    assert recorder.external == []
