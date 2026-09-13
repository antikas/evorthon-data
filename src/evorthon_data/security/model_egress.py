"""Fail-closed authorization gateway for every model-egress route.

This module is the one product owner of the decision to send a model request
outside the local process.  Callers describe a request and, for external
egress, present an explicitly scoped authorization.  The adopting environment
then attests the currently authenticated identity and revocation state.  A
provider client is deliberately private to :class:`ModelEgressGateway`; product
consumers receive only the ``ModelEgressPort`` invocation surface.
"""
from __future__ import annotations

# evorthon-component: security_model_egress

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable


class ModelCallPurpose(str, Enum):
    """The only product roles allowed to request a model invocation."""

    GENERATOR = "generator"
    REVIEWER = "reviewer"
    ADVISER = "adviser"


class ModelEgressMode(str, Enum):
    """Execution boundary selected by product composition, not by a provider."""

    LOCAL = "local"
    FAKE = "fake"
    EXTERNAL = "external"


class EgressDenialReason(str, Enum):
    """Stable, payload-free reasons for an external egress refusal."""

    AUTHORIZATION_REQUIRED = "authorization_required"
    AUTHORIZATION_NOT_CURRENT = "authorization_not_current"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    SCOPE_MISMATCH = "scope_mismatch"
    VALIDATION_FAILED = "environment_validation_failed"
    VALIDATION_NOT_CURRENT = "environment_validation_not_current"
    AUTHENTICATION_REQUIRED = "authenticated_identity_required"
    AUTHENTICATION_MISMATCH = "authenticated_identity_mismatch"
    AUTHORIZATION_REVOKED = "authorization_revoked"
    EXTERNAL_TRANSPORT_UNAVAILABLE = "external_transport_unavailable"


class ModelEgressDenied(PermissionError):
    """Raised before an external transport receives an unauthorized request."""

    def __init__(self, reason: EgressDenialReason):
        self.reason = reason
        super().__init__(f"model egress denied: {reason.value}")


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty, trimmed string")
    if any(character in value for character in ("\n", "\r", "\x00")):
        raise ValueError(f"{field_name} must not contain a control character")
    return value


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _field_mapping(fields: Mapping[str, object], field_name: str) -> Mapping[str, object]:
    if not isinstance(fields, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    normalized: dict[str, object] = {}
    for key, value in fields.items():
        normalized_key = _required_text(key, f"{field_name} key")
        if normalized_key in normalized:
            raise ValueError(f"{field_name} contains a duplicate field")
        normalized[normalized_key] = value
    if not normalized:
        raise ValueError(f"{field_name} must name at least one field")
    return MappingProxyType(normalized)


@dataclass(frozen=True)
class ModelDestination:
    """The provider and exact destination a request is allowed to reach."""

    provider: str
    endpoint: str
    model: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _required_text(self.provider, "provider"))
        object.__setattr__(self, "endpoint", _required_text(self.endpoint, "endpoint"))
        object.__setattr__(self, "model", _required_text(self.model, "model"))


@dataclass(frozen=True)
class ModelCall:
    """A bounded request which carries only the fields selected for the call."""

    engagement_id: str
    case_id: str
    purpose: ModelCallPurpose
    route: str
    destination: ModelDestination
    fields: Mapping[str, object]
    data_class: str
    retention_policy: str
    evidence_policy: str
    mode: ModelEgressMode

    def __post_init__(self) -> None:
        object.__setattr__(self, "engagement_id", _required_text(self.engagement_id, "engagement_id"))
        object.__setattr__(self, "case_id", _required_text(self.case_id, "case_id"))
        if not isinstance(self.purpose, ModelCallPurpose):
            raise ValueError("purpose must be a ModelCallPurpose")
        object.__setattr__(self, "route", _required_text(self.route, "route"))
        if not isinstance(self.destination, ModelDestination):
            raise ValueError("destination must be a ModelDestination")
        object.__setattr__(self, "fields", _field_mapping(self.fields, "fields"))
        object.__setattr__(self, "data_class", _required_text(self.data_class, "data_class"))
        object.__setattr__(self, "retention_policy", _required_text(self.retention_policy, "retention_policy"))
        object.__setattr__(self, "evidence_policy", _required_text(self.evidence_policy, "evidence_policy"))
        if not isinstance(self.mode, ModelEgressMode):
            raise ValueError("mode must be a ModelEgressMode")

    @property
    def field_inventory(self) -> frozenset[str]:
        """Return the complete field set sent to the selected transport."""
        return frozenset(self.fields)


@dataclass(frozen=True)
class ModelEgressAuthorization:
    """A human/environment-issued scope; it is not an ambient credential."""

    authorization_id: str
    engagement_id: str
    case_id: str
    purpose: ModelCallPurpose
    route: str
    destination: ModelDestination
    permitted_fields: frozenset[str]
    data_class: str
    retention_policy: str
    evidence_policy: str
    expected_authenticated_identity: str
    not_before: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorization_id", _required_text(self.authorization_id, "authorization_id"))
        object.__setattr__(self, "engagement_id", _required_text(self.engagement_id, "engagement_id"))
        object.__setattr__(self, "case_id", _required_text(self.case_id, "case_id"))
        if not isinstance(self.purpose, ModelCallPurpose):
            raise ValueError("purpose must be a ModelCallPurpose")
        object.__setattr__(self, "route", _required_text(self.route, "route"))
        if not isinstance(self.destination, ModelDestination):
            raise ValueError("destination must be a ModelDestination")
        if not isinstance(self.permitted_fields, frozenset):
            raise ValueError("permitted_fields must be a frozenset")
        if not self.permitted_fields or any(not isinstance(field, str) for field in self.permitted_fields):
            raise ValueError("permitted_fields must contain field names")
        object.__setattr__(
            self,
            "permitted_fields",
            frozenset(_required_text(field, "permitted_fields item") for field in self.permitted_fields),
        )
        object.__setattr__(self, "data_class", _required_text(self.data_class, "data_class"))
        object.__setattr__(self, "retention_policy", _required_text(self.retention_policy, "retention_policy"))
        object.__setattr__(self, "evidence_policy", _required_text(self.evidence_policy, "evidence_policy"))
        object.__setattr__(
            self,
            "expected_authenticated_identity",
            _required_text(self.expected_authenticated_identity, "expected_authenticated_identity"),
        )
        not_before = _aware_utc(self.not_before, "not_before")
        expires_at = _aware_utc(self.expires_at, "expires_at")
        if expires_at <= not_before:
            raise ValueError("expires_at must be after not_before")
        object.__setattr__(self, "not_before", not_before)
        object.__setattr__(self, "expires_at", expires_at)


@dataclass(frozen=True)
class AuthorizationValidation:
    """Current authorization facts supplied by the adopting environment."""

    authorization_id: str
    authenticated_identity: str | None
    valid: bool
    revoked: bool
    checked_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorization_id", _required_text(self.authorization_id, "authorization_id"))
        if self.authenticated_identity is not None:
            object.__setattr__(
                self,
                "authenticated_identity",
                _required_text(self.authenticated_identity, "authenticated_identity"),
            )
        if not isinstance(self.valid, bool) or not isinstance(self.revoked, bool):
            raise ValueError("valid and revoked must be bool values")
        object.__setattr__(self, "checked_at", _aware_utc(self.checked_at, "checked_at"))


@runtime_checkable
class EnvironmentAuthorizationValidator(Protocol):
    """Environment-owned source for current identity, validity and revocation."""

    def validate(self, authorization: ModelEgressAuthorization, *, at: datetime) -> AuthorizationValidation:
        """Return the current status for this exact authorization."""


@runtime_checkable
class ModelEgressPort(Protocol):
    """The only model-invocation capability given to product consumers."""

    def invoke(self, request: ModelCall, authorization: ModelEgressAuthorization | None = None) -> Any:
        """Run a local/fake request or authorize an external request."""


class ModelEgressGateway:
    """Route local/fake calls and fail closed before external model egress.

    The transport callables are constructor-only composition details.  The
    public ``invoke`` method deliberately does not accept a transport, provider
    client, credential or harness session, so a consumer cannot select an
    external route outside this gateway.
    """

    def __init__(
        self,
        *,
        local_transport: Callable[[ModelCall], Any],
        fake_transport: Callable[[ModelCall], Any] | None = None,
        external_transport: Callable[[ModelCall], Any] | None = None,
        authorization_validator: EnvironmentAuthorizationValidator | None = None,
        clock: Callable[[], datetime] | None = None,
        max_validation_age: timedelta = timedelta(seconds=60),
    ) -> None:
        if not callable(local_transport):
            raise ValueError("local_transport must be callable")
        if fake_transport is not None and not callable(fake_transport):
            raise ValueError("fake_transport must be callable when supplied")
        if external_transport is not None and not callable(external_transport):
            raise ValueError("external_transport must be callable when supplied")
        if authorization_validator is not None and not isinstance(authorization_validator, EnvironmentAuthorizationValidator):
            raise ValueError("authorization_validator must implement EnvironmentAuthorizationValidator")
        if clock is not None and not callable(clock):
            raise ValueError("clock must be callable when supplied")
        if not isinstance(max_validation_age, timedelta) or max_validation_age <= timedelta(0):
            raise ValueError("max_validation_age must be positive")
        self.__local_transport = local_transport
        self.__fake_transport = fake_transport or local_transport
        self.__external_transport = external_transport
        self.__authorization_validator = authorization_validator
        self.__clock = clock or (lambda: datetime.now(timezone.utc))
        self.__max_validation_age = max_validation_age

    def invoke(self, request: ModelCall, authorization: ModelEgressAuthorization | None = None) -> Any:
        """Invoke exactly one configured transport after the required checks."""
        if not isinstance(request, ModelCall):
            raise ValueError("request must be a ModelCall")
        if authorization is not None and not isinstance(authorization, ModelEgressAuthorization):
            raise ValueError("authorization must be a ModelEgressAuthorization when supplied")
        if request.mode is ModelEgressMode.LOCAL:
            return self.__local_transport(request)
        if request.mode is ModelEgressMode.FAKE:
            return self.__fake_transport(request)

        self.__authorize_external(request, authorization)
        if self.__external_transport is None:
            raise ModelEgressDenied(EgressDenialReason.EXTERNAL_TRANSPORT_UNAVAILABLE)
        return self.__external_transport(request)

    def __authorize_external(self, request: ModelCall, authorization: ModelEgressAuthorization | None) -> None:
        if authorization is None:
            raise ModelEgressDenied(EgressDenialReason.AUTHORIZATION_REQUIRED)
        now = _aware_utc(self.__clock(), "clock result")
        if now < authorization.not_before:
            raise ModelEgressDenied(EgressDenialReason.AUTHORIZATION_NOT_CURRENT)
        if now >= authorization.expires_at:
            raise ModelEgressDenied(EgressDenialReason.AUTHORIZATION_EXPIRED)
        if not self.__scope_matches(request, authorization):
            raise ModelEgressDenied(EgressDenialReason.SCOPE_MISMATCH)
        if self.__authorization_validator is None:
            raise ModelEgressDenied(EgressDenialReason.VALIDATION_FAILED)

        try:
            validation = self.__authorization_validator.validate(authorization, at=now)
        except Exception as exc:
            raise ModelEgressDenied(EgressDenialReason.VALIDATION_FAILED) from exc
        if not isinstance(validation, AuthorizationValidation):
            raise ModelEgressDenied(EgressDenialReason.VALIDATION_FAILED)
        if validation.authorization_id != authorization.authorization_id:
            raise ModelEgressDenied(EgressDenialReason.VALIDATION_FAILED)
        if validation.checked_at > now or now - validation.checked_at > self.__max_validation_age:
            raise ModelEgressDenied(EgressDenialReason.VALIDATION_NOT_CURRENT)
        if validation.revoked:
            raise ModelEgressDenied(EgressDenialReason.AUTHORIZATION_REVOKED)
        if not validation.valid:
            raise ModelEgressDenied(EgressDenialReason.VALIDATION_FAILED)
        if validation.authenticated_identity is None:
            raise ModelEgressDenied(EgressDenialReason.AUTHENTICATION_REQUIRED)
        if validation.authenticated_identity != authorization.expected_authenticated_identity:
            raise ModelEgressDenied(EgressDenialReason.AUTHENTICATION_MISMATCH)

    @staticmethod
    def __scope_matches(request: ModelCall, authorization: ModelEgressAuthorization) -> bool:
        return (
            request.engagement_id == authorization.engagement_id
            and request.case_id == authorization.case_id
            and request.purpose is authorization.purpose
            and request.route == authorization.route
            and request.destination == authorization.destination
            and request.field_inventory == authorization.permitted_fields
            and request.data_class == authorization.data_class
            and request.retention_policy == authorization.retention_policy
            and request.evidence_policy == authorization.evidence_policy
        )
