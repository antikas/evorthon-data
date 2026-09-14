"""One owner for the machine-route, credential and raw-row shapes, read at every boundary.

Four places in this product decide whether a text carries a route to somebody's
machine: the use-case aggregate reading a fact locator, the privacy gate
reading a fault packet, the public-candidate scan reading a shipped file, and
the tracker adapter reading a note. This file proves they read the same
declared shapes, that the shapes have one owner, and that every allowance a
boundary keeps is one its own module states with the reason for it.

A fifth family is advisory. One boundary reads it, for a label and never for a
refusal, and this file proves that no boundary refuses on it and that both
released sentences say so clause by clause.

The probe values are assembled from character codes so this file, which ships
in the public candidate and is scanned there, carries no route of its own.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from evorthon_data import boundary_patterns as owner
from evorthon_data import public_boundary
from evorthon_data.delivery import pinax
from evorthon_data.engagement import (
    FactLocator,
    ImmutableReference,
    ReferenceKind,
    UseCaseError,
)
from evorthon_data.koine_session import CREDENTIAL_PATTERNS as INTAKE_CREDENTIALS
from evorthon_data.koine_session import LOCATOR_ADVISORY_SHAPES
from evorthon_data.public_boundary import scan_candidate
from evorthon_data.verification.domain.contracts import (
    DiagnosticLocalisation,
    DisclosureDecision,
    EvidenceReference,
    FaultClass,
    FaultRecord,
    Identity,
    LocalisationStatus,
)
from evorthon_data.verification.enforcement.privacy import (
    CREDENTIAL_PATTERNS as GATE_CREDENTIALS,
)
from evorthon_data.verification.enforcement.privacy import (
    LOCAL_PATH_PATTERNS,
    RAW_ROW_PATTERNS,
    PrivacyRefusalReason,
    PrivacyRefused,
    gate_fault_packet,
)

ROOT = Path(__file__).parents[2]
SOURCE_ROOT = ROOT / "src" / "evorthon_data"
OWNER_MODULE = SOURCE_ROOT / "boundary_patterns.py"

MARK = chr(58)
ESCAPE = chr(92)
STOP = chr(46)
FINGERPRINT = "blake2b-256" + MARK + "ab" * 32

# The eight forms a text can carry a machine route in, each driven through all
# four boundaries. Seven are machine routes and are refused everywhere. The
# eighth is the drawing namespace every generated diagram declares, which the
# public scan allows and every other boundary refuses, because no locator, no
# packet and no tracker note has any reason to carry a web address at all.
INTERNAL_WEB_ADDRESS = "http" + MARK + "//estate.example/orders"
FILE_ADDRESS = "file" + MARK + "//estate/orders.csv"
TRAVERSAL = STOP * 2 + "/estate/orders.csv"
HOME_PATH = "/" + "home" + "/analyst/orders.csv"
NETWORK_SHARE_PATH = ESCAPE * 2 + "estate-server" + ESCAPE + "orders"
DRIVE_PATH = "D" + MARK + "/estate/orders.csv"
BACKSLASH_RELATIVE_PATH = "estate" + ESCAPE + "extracts" + ESCAPE + "orders.csv"
DRAWING_NAMESPACE = "http" + MARK + "//www.w3.org/2000/svg"

MACHINE_ROUTE_PROBES = (
    ("an internal web address", INTERNAL_WEB_ADDRESS, owner.WEB_ADDRESS),
    ("a file scheme", FILE_ADDRESS, owner.LOCAL_FILE_ADDRESS),
    ("a traversal", TRAVERSAL, owner.TRAVERSAL),
    ("a home path", HOME_PATH, owner.USER_HOME_PATH),
    ("a network share path", NETWORK_SHARE_PATH, owner.NETWORK_SHARE_PATH),
    ("a drive path", DRIVE_PATH, owner.DRIVE_PATH),
    ("a backslash-relative path", BACKSLASH_RELATIVE_PATH, owner.BACKSLASH_RELATIVE_PATH),
)
PROBE_IDS = [name for name, _, _ in MACHINE_ROUTE_PROBES]
PROBE_VALUES = [value for _, value, _ in MACHINE_ROUTE_PROBES]

# The ten further forms a locator, a packet and a note must not carry. Six are
# addresses under a scheme this product had named nowhere, which is how a cloud
# store, an object store, a transfer, a share, a lake and a database are
# written. Four are the forms a declared value writes a machine path in, which
# a page of shipped prose writes for other reasons and the scan therefore
# leaves unread.
CLOUD_STORE_ADDRESS = "abfss" + MARK + "//raw@acct.dfs.core.windows.net/pii-extract.csv"
OBJECT_STORE_ADDRESS = "s3" + MARK + "//acme-prod-exports/customer-pii.csv"
TRANSFER_ADDRESS = "ftp" + MARK + "//10.4.2.9/pii.csv"
SHARE_ADDRESS = "smb" + MARK + "//fileserver/share"
LAKE_ADDRESS = "gs" + MARK + "//bucket/pii.csv"
DATABASE_ADDRESS = "jdbc" + MARK + "//host/db"
PROSE_ABSOLUTE_PATH = "/estate/extracts/orders.csv"
SINGLE_SEGMENT_ABSOLUTE_PATH = "/exports"
DRIVE_RELATIVE_PATH = "D" + MARK + "pii.csv"
NETWORK_SHARE_HOST = ESCAPE * 2 + "fileserver"
EMBEDDED_TRAVERSAL = "intake/" + STOP * 2 + "/" + STOP * 2 + "/srv/exports/pii.csv"

SCHEME_PROBES = (
    ("a cloud store address", CLOUD_STORE_ADDRESS),
    ("an object store address", OBJECT_STORE_ADDRESS),
    ("a transfer address", TRANSFER_ADDRESS),
    ("a share address", SHARE_ADDRESS),
    ("a lake address", LAKE_ADDRESS),
    ("a database address", DATABASE_ADDRESS),
)
SCHEME_PROBE_IDS = [name for name, _ in SCHEME_PROBES]
SCHEME_PROBE_VALUES = [value for _, value in SCHEME_PROBES]

DECLARED_VALUE_PROBES = (
    ("a single-segment absolute path", SINGLE_SEGMENT_ABSOLUTE_PATH, owner.DECLARED_ABSOLUTE_PATH),
    ("a drive-relative path", DRIVE_RELATIVE_PATH, owner.DRIVE_RELATIVE_PATH),
    ("a network share host", NETWORK_SHARE_HOST, owner.NETWORK_SHARE_HOST),
    ("an embedded traversal", EMBEDDED_TRAVERSAL, owner.DECLARED_TRAVERSAL),
)
DECLARED_VALUE_PROBE_IDS = [name for name, _, _ in DECLARED_VALUE_PROBES]
DECLARED_VALUE_PROBE_VALUES = [value for _, value, _ in DECLARED_VALUE_PROBES]

# The three values a locator can carry an address in with no scheme in front of
# it. No reading tells a dotted name from an ordinary written name, so every
# boundary admits all three and the advisory family labels them instead.
BARE_STORE_ADDRESS = (
    "acct" + STOP + "dfs" + STOP + "core" + STOP + "windows" + STOP + "net/customers/pii-extract.csv"
)
BARE_HOST_AND_PORT = "db-prod" + STOP + "internal" + MARK + "5432"
WRITTEN_CONNECTION_STRING = (
    "Server=db-prod" + STOP + "internal,1433;Database=warehouse;Trusted_Connection=True"
)

ADVISORY_PROBES = (
    ("a bare store address", BARE_STORE_ADDRESS, owner.BARE_HOST),
    ("a bare host and port", BARE_HOST_AND_PORT, owner.BARE_HOST),
    ("a connection string", WRITTEN_CONNECTION_STRING, owner.CONNECTION_STRING),
)
ADVISORY_PROBE_IDS = [name for name, _, _ in ADVISORY_PROBES]
ADVISORY_PROBE_VALUES = [value for _, value, _ in ADVISORY_PROBES]

# The benign declared values two widened shapes used to refuse. A spreadsheet
# column range is an ordinary position inside an artefact and a rate is ordinary
# prose, so every boundary admits them and nothing warns on them.
BENIGN_DECLARED_VALUES = (
    ("a column range", "A" + MARK + "B"),
    ("a named column range", "Sheet1!A" + MARK + "B"),
    ("a described column range", "column range C" + MARK + "F"),
    ("a short written value", "q" + MARK + "4 totals"),
    ("a rate", "the rate is 60 /hour"),
)
BENIGN_IDS = [name for name, _ in BENIGN_DECLARED_VALUES]
BENIGN_VALUES = [value for _, value in BENIGN_DECLARED_VALUES]

# Each narrowed shape, the benign value it stopped reading, and the route it
# still reads. A narrowing that swallowed its route would redden here.
NARROWED_SHAPES = (
    ("the lettered volume", owner.DRIVE_RELATIVE_PATH, "A" + MARK + "B", DRIVE_RELATIVE_PATH),
    ("the declared path from the root", owner.DECLARED_ABSOLUTE_PATH, "the rate is 60 /hour", SINGLE_SEGMENT_ABSOLUTE_PATH),
)
NARROWED_IDS = [name for name, _, _, _ in NARROWED_SHAPES]

# The adoption guide owns the detailed refusal list; the README links to it.
RELEASED_SURFACES = ("ADOPTION-GUIDE.md",)
CLAUSE_ANCHOR = "an address under any scheme"
# Every clause of that list, with a probe carrying it and the shape the one
# owner declares for that probe. A clause the sentence adds with no shape behind
# it, a declared shape with no clause in front of it, or a probe the record
# admits, each redden this table.
REFUSED_CLAUSES = (
    ("an address under any scheme", INTERNAL_WEB_ADDRESS, owner.WEB_ADDRESS),
    ("an address under any scheme", FILE_ADDRESS, owner.LOCAL_FILE_ADDRESS),
    ("an address under any scheme", CLOUD_STORE_ADDRESS, owner.SCHEME_ADDRESS),
    ("a path from the root of a machine", PROSE_ABSOLUTE_PATH, owner.ABSOLUTE_PATH),
    ("a path from the root of a machine", SINGLE_SEGMENT_ABSOLUTE_PATH, owner.DECLARED_ABSOLUTE_PATH),
    ("a lettered volume", DRIVE_PATH, owner.DRIVE_PATH),
    ("a lettered volume", DRIVE_RELATIVE_PATH, owner.DRIVE_RELATIVE_PATH),
    ("a share host", NETWORK_SHARE_PATH, owner.NETWORK_SHARE_PATH),
    ("a share host", NETWORK_SHARE_HOST, owner.NETWORK_SHARE_HOST),
    ("a written home directory", HOME_PATH, owner.USER_HOME_PATH),
    ("a climb out of where it starts", TRAVERSAL, owner.TRAVERSAL),
    ("a climb out of where it starts", EMBEDDED_TRAVERSAL, owner.DECLARED_TRAVERSAL),
    (
        "a path written with a machine path's separator",
        BACKSLASH_RELATIVE_PATH,
        owner.BACKSLASH_RELATIVE_PATH,
    ),
)
CLAUSE_IDS = [f"{clause}, as {shape}" for clause, _, shape in REFUSED_CLAUSES]
# The guide clauses that state what is admitted and
# labelled instead of refused.
WARNED_CLAUSES = (
    "a locator that reads like a dotted server name followed by a path or a port",
    "or like a connection string",
    "reports a warning on it",
    "a dotted name cannot be told from an ordinary written name",
    "keep actual connection details in environment configuration",
    "the warning leaves the locator admitted",
)

# One probe per shape this correction added, each caught by that shape alone.
RESTORED_SHAPE_PROBES = (
    ("the scheme shape", owner.SCHEME_ADDRESS, CLOUD_STORE_ADDRESS),
    ("the declared absolute path", owner.DECLARED_ABSOLUTE_PATH, SINGLE_SEGMENT_ABSOLUTE_PATH),
    ("the drive-relative path", owner.DRIVE_RELATIVE_PATH, DRIVE_RELATIVE_PATH),
    ("the network share host", owner.NETWORK_SHARE_HOST, NETWORK_SHARE_HOST),
    ("the declared traversal", owner.DECLARED_TRAVERSAL, EMBEDDED_TRAVERSAL),
)
RESTORED_SHAPE_IDS = [name for name, _, _ in RESTORED_SHAPE_PROBES]


# --- The four boundaries, each asked the same question ---


def aggregate_refusal(value: str) -> str:
    """The refusal the use-case aggregate gives for the value as a fact locator."""
    artefact = ImmutableReference(
        kind=ReferenceKind.INTAKE_ARTEFACT,
        identifier="order-extract-workbook",
        version="v1",
        digest="digest-order-extract-workbook",
    )
    try:
        FactLocator(artefact=artefact, position=value)
    except UseCaseError as refusal:
        return str(refusal)
    return ""


def aggregate_refuses(value: str) -> bool:
    """Whether the use-case aggregate refuses the value as a fact locator."""
    return "must be logical" in aggregate_refusal(value)


def packet(scope: str):
    """Return the smallest fault packet the privacy gate will read in full."""
    return FaultRecord(
        fault_id="fault-daily-orders",
        version="evorthon.fault.v1",
        result=Identity(identifier="result-daily-orders", version="v1", digest=FINGERPRINT),
        affected_clause_outcome_ids=("clause-row-count",),
        fault_class=FaultClass.MISSING_POPULATION,
        localisation=DiagnosticLocalisation(
            localisation_id="localisation-daily-orders",
            version="v1",
            status=LocalisationStatus.INFERRED,
            lower_frontier=(),
            upper_frontier=(),
            uncovered_paths=(),
            supporting_evidence=(),
        ),
        diagnostic_scope=scope,
        disclosure_decision=DisclosureDecision.DISCLOSE,
        supporting_evidence=(
            EvidenceReference(
                evidence_id="evidence-daily-orders",
                version="v1",
                digest=FINGERPRINT,
                summary="the declared row counts differ",
            ),
        ),
        contradicting_evidence=(),
        correction_surface=None,
    )


def gate_refuses(value: str) -> bool:
    """Whether the privacy gate refuses a packet whose scope carries the value."""
    try:
        gate_fault_packet(packet(f"output daily-orders; {value}"))
    except PrivacyRefused as refusal:
        return refusal.reason is PrivacyRefusalReason.LOCAL_PATH
    return False


def scan_refuses(value: str, root: Path, *, name: str = "candidate-note.txt") -> bool:
    """Whether the public-candidate scan reports a shipped file carrying the value."""
    (root / public_boundary.POLICY).write_text(
        json.dumps({"forbidden_token_hashes": []}), encoding="utf-8"
    )
    (root / name).write_text(value + "\n", encoding="utf-8")
    return any(finding.endswith(name) for finding in scan_candidate(root))


def tracker_refuses(value: str) -> bool:
    """Whether the tracker adapter refuses the value in a note it would write."""
    try:
        pinax._tracker_text(value, "a tracker note")
    except pinax.PinaxProjectionError as refusal:
        return "not a machine route" in str(refusal)
    return False


def gate_refusal_reason(value: str) -> PrivacyRefusalReason | None:
    """The closed reason the privacy gate refuses the value under, or nothing."""
    try:
        gate_fault_packet(packet(f"output daily-orders; {value}"))
    except PrivacyRefused as refusal:
        return refusal.reason
    return None


def tracker_admits(value: str) -> bool:
    """Whether the tracker adapter lets the value through for any reason at all."""
    try:
        pinax._tracker_text(value, "a tracker note")
    except pinax.PinaxProjectionError:
        return False
    return True


def advisory_shape(value: str) -> str | None:
    """The advisory shape the one owner labels the value with, or nothing."""
    return owner.shape_carried(owner.shapes(owner.ADVISORY_PATTERNS, owner.ADVISORY_SHAPES), value)


def route_shape(value: str) -> str | None:
    """The machine-route shape the one owner declares for the value, or nothing."""
    return owner.shape_carried(
        owner.shapes(owner.MACHINE_ROUTE_PATTERNS, owner.MACHINE_ROUTE_SHAPES), value
    )


def released_refusal_clauses(relative: str) -> tuple[str, ...]:
    """Read the refusal list from the adoption guide, clause by clause."""
    text = (ROOT / relative).read_text(encoding="utf-8")
    start = text.index("- " + CLAUSE_ANCHOR)
    listed = text[start : text.index("\n\n", start)]
    return tuple(line.removeprefix("- ").strip() for line in listed.splitlines())


# --- Every boundary reads the same shapes ---


def test_the_owner_declares_the_four_closed_families_and_nothing_else():
    assert owner.MACHINE_ROUTE_SHAPES == (
        owner.DRIVE_PATH,
        owner.DRIVE_RELATIVE_PATH,
        owner.NETWORK_SHARE_PATH,
        owner.NETWORK_SHARE_HOST,
        owner.USER_HOME_PATH,
        owner.ABSOLUTE_PATH,
        owner.DECLARED_ABSOLUTE_PATH,
        owner.LOCAL_FILE_ADDRESS,
        owner.WEB_ADDRESS,
        owner.SCHEME_ADDRESS,
        owner.TRAVERSAL,
        owner.DECLARED_TRAVERSAL,
        owner.BACKSLASH_RELATIVE_PATH,
    )
    assert owner.CREDENTIAL_SHAPES == (
        owner.NAMED_SECRET,
        owner.NAMED_KEY,
        owner.PRESENTED_TOKEN,
        owner.KEY_BLOCK,
        owner.ASSIGNED_SECRET,
        owner.CONNECTION_CREDENTIAL,
        owner.BEARER_AUTHORIZATION,
    )
    assert owner.RAW_ROW_SHAPES == (
        owner.CONTROL_CHARACTER,
        owner.WRITTEN_OBJECT,
        owner.DELIMITED_FIELDS,
    )
    assert owner.ADVISORY_SHAPES == (owner.BARE_HOST, owner.CONNECTION_STRING)


@pytest.mark.parametrize(
    ("value", "shape"),
    [(value, shape) for _, value, shape in MACHINE_ROUTE_PROBES],
    ids=PROBE_IDS,
)
def test_each_probe_carries_the_shape_the_owner_declares_for_it(value, shape):
    read = owner.shapes(owner.MACHINE_ROUTE_PATTERNS, owner.MACHINE_ROUTE_SHAPES)

    assert owner.shape_carried(read, value) == shape


@pytest.mark.parametrize("value", PROBE_VALUES, ids=PROBE_IDS)
def test_the_use_case_aggregate_refuses_every_declared_machine_route(value):
    assert aggregate_refuses(value)


@pytest.mark.parametrize("value", PROBE_VALUES, ids=PROBE_IDS)
def test_the_privacy_gate_refuses_every_declared_machine_route(value):
    assert gate_refuses(value)


@pytest.mark.parametrize("value", PROBE_VALUES, ids=PROBE_IDS)
def test_the_public_candidate_scan_reports_every_declared_machine_route(value, tmp_path):
    assert scan_refuses(value, tmp_path)


@pytest.mark.parametrize("value", PROBE_VALUES, ids=PROBE_IDS)
def test_the_tracker_adapter_refuses_every_declared_machine_route(value):
    assert tracker_refuses(value)


def test_the_drawing_namespace_is_allowed_only_where_the_scan_reads_shipped_text(tmp_path):
    """The eighth probe. The scan allows it; a locator, a packet and a note do not."""
    assert not scan_refuses(DRAWING_NAMESPACE, tmp_path)
    assert aggregate_refuses(DRAWING_NAMESPACE)
    assert gate_refuses(DRAWING_NAMESPACE)
    assert tracker_refuses(DRAWING_NAMESPACE)


def test_a_secure_public_address_is_allowed_only_where_the_scan_reads_shipped_text(tmp_path):
    """The other half of the scan's first allowance: documentation links out."""
    published = "https" + MARK + "//example.org/evorthon-data"

    assert not scan_refuses(published, tmp_path)
    assert aggregate_refuses(published)
    assert gate_refuses(published)
    assert tracker_refuses(published)


def test_the_scan_does_not_read_a_backslash_separator_in_escape_carrying_source(tmp_path):
    """The scan's third allowance, with the reason it exists in its own module."""
    assert not scan_refuses(BACKSLASH_RELATIVE_PATH, tmp_path, name="module.py")
    assert scan_refuses(BACKSLASH_RELATIVE_PATH, tmp_path, name="guide.md")
    assert public_boundary.ESCAPED_SUFFIXES == {".py", ".json", ".canonical"}


def test_the_scan_does_not_read_the_five_declared_value_shapes():
    """The scan's third allowance: these forms are ordinary shipped prose."""
    assert public_boundary.UNREAD_SHAPES == (
        owner.ABSOLUTE_PATH,
        owner.DECLARED_ABSOLUTE_PATH,
        owner.DRIVE_RELATIVE_PATH,
        owner.NETWORK_SHARE_HOST,
        owner.DECLARED_TRAVERSAL,
    )
    for shape in public_boundary.UNREAD_SHAPES:
        assert shape not in public_boundary.SCANNED_SHAPES
    for boundary in (aggregate_refuses, gate_refuses, tracker_refuses):
        assert boundary("/estate/extracts/orders.csv")


# --- The three forms a fact locator used to admit ---


def test_the_aggregate_refuses_an_internal_web_address_a_file_scheme_and_a_traversal():
    for admitted in (INTERNAL_WEB_ADDRESS, FILE_ADDRESS, TRAVERSAL):
        assert aggregate_refuses(admitted)
        assert gate_refuses(admitted)
        assert tracker_refuses(admitted)


# --- An address under any scheme at all ---


@pytest.mark.parametrize("value", SCHEME_PROBE_VALUES, ids=SCHEME_PROBE_IDS)
def test_the_use_case_aggregate_refuses_an_address_under_any_scheme(value):
    """A locator names a record, so it carries no address under any scheme."""
    assert aggregate_refuses(value)


@pytest.mark.parametrize("value", SCHEME_PROBE_VALUES, ids=SCHEME_PROBE_IDS)
def test_the_privacy_gate_refuses_an_address_under_any_scheme(value):
    assert gate_refuses(value)


@pytest.mark.parametrize("value", SCHEME_PROBE_VALUES, ids=SCHEME_PROBE_IDS)
def test_the_tracker_adapter_refuses_an_address_under_any_scheme(value):
    assert tracker_refuses(value)


@pytest.mark.parametrize("value", SCHEME_PROBE_VALUES, ids=SCHEME_PROBE_IDS)
def test_the_scan_reports_an_address_under_a_scheme_it_does_not_name(value, tmp_path):
    assert scan_refuses(value, tmp_path)


def test_the_scan_allows_the_two_web_schemes_and_this_product_s_composed_reference(tmp_path):
    """The scan's allowed address forms, and nothing else under a scheme."""
    assert owner.NAMED_SCHEME_FORMS == (
        owner.SECURE_WEB_SCHEME,
        owner.INSECURE_WEB_SCHEME,
        owner.LOCAL_FILE_SCHEME,
    )
    assert owner.LOGICAL_REFERENCE_FORM == owner.LOGICAL_REFERENCE_SCHEME + owner.LOGICAL_REFERENCE_ROOT
    assert owner.ALLOWED_SCHEME_FORMS == (
        owner.SECURE_WEB_SCHEME,
        owner.LOGICAL_REFERENCE_FORM,
    )
    reference = owner.LOGICAL_REFERENCE_FORM + "orders/readiness/" + "ab" * 32

    assert not scan_refuses(reference, tmp_path, name="reference-note.md")
    assert aggregate_refuses(reference)
    assert gate_refuses(reference)
    assert tracker_refuses(reference)


@pytest.mark.parametrize(
    "host",
    ["otherhost/x", "[" + MARK * 2 + "1]/x", "-otherhost/x", "_otherhost/x"],
    ids=["a named host", "a bracketed address", "a leading mark", "a leading underscore"],
)
def test_the_scan_reports_this_product_s_scheme_in_front_of_a_host(host, tmp_path):
    """The allowance is the composed form, so the scheme cannot carry a host.

    However the host is spelled, the scheme in front of it is reported. Only the
    composed form, and the scheme with no name after it, are allowed.
    """
    assert scan_refuses(owner.LOGICAL_REFERENCE_SCHEME + host, tmp_path, name="reference-note.md")


def test_the_scan_allows_this_product_s_scheme_named_with_nothing_after_it(tmp_path):
    """The adapter contract states the form the tracker accepts, and names no host."""
    stated = "a reference must start with `" + owner.LOGICAL_REFERENCE_SCHEME + "`, and nothing else"

    assert not scan_refuses(stated, tmp_path, name="contract.md")


def test_the_scan_reports_one_finding_for_an_address_it_names(tmp_path):
    """The file and web schemes keep the names the published evidence carries."""
    (tmp_path / public_boundary.POLICY).write_text(
        json.dumps({"forbidden_token_hashes": []}), encoding="utf-8"
    )
    (tmp_path / "note.txt").write_text(FILE_ADDRESS + "\n", encoding="utf-8")
    file_findings = [item for item in scan_candidate(tmp_path) if item.endswith("note.txt")]
    (tmp_path / "note.txt").write_text(INTERNAL_WEB_ADDRESS + "\n", encoding="utf-8")
    web_findings = [item for item in scan_candidate(tmp_path) if item.endswith("note.txt")]

    assert file_findings == ["file URL: note.txt"]
    assert web_findings == ["non-public HTTP URL: note.txt"]


# --- The four forms a declared value writes a machine path in ---


@pytest.mark.parametrize("value", DECLARED_VALUE_PROBE_VALUES, ids=DECLARED_VALUE_PROBE_IDS)
def test_the_use_case_aggregate_refuses_a_declared_value_form(value):
    """A declared value is not prose, so the prose allowances do not reach it."""
    assert aggregate_refuses(value)


@pytest.mark.parametrize("value", DECLARED_VALUE_PROBE_VALUES, ids=DECLARED_VALUE_PROBE_IDS)
def test_the_privacy_gate_refuses_a_declared_value_form(value):
    assert gate_refuses(value)


@pytest.mark.parametrize("value", DECLARED_VALUE_PROBE_VALUES, ids=DECLARED_VALUE_PROBE_IDS)
def test_the_tracker_adapter_refuses_a_declared_value_form(value):
    assert tracker_refuses(value)


@pytest.mark.parametrize("value", DECLARED_VALUE_PROBE_VALUES, ids=DECLARED_VALUE_PROBE_IDS)
def test_the_scan_leaves_a_declared_value_form_unread_in_shipped_prose(value, tmp_path):
    assert not scan_refuses(value, tmp_path, name="guide.md")


@pytest.mark.parametrize(
    ("value", "shape"),
    [(value, shape) for _, value, shape in DECLARED_VALUE_PROBES],
    ids=DECLARED_VALUE_PROBE_IDS,
)
def test_each_declared_value_probe_carries_the_shape_the_owner_declares_for_it(value, shape):
    read = owner.shapes(owner.MACHINE_ROUTE_PATTERNS, owner.MACHINE_ROUTE_SHAPES)

    assert owner.shape_carried(read, value) == shape


# --- An address with no scheme in front of it: admitted, and labelled ---


@pytest.mark.parametrize(
    ("value", "shape"),
    [(value, shape) for _, value, shape in ADVISORY_PROBES],
    ids=ADVISORY_PROBE_IDS,
)
def test_the_owner_labels_an_address_that_carries_no_scheme(value, shape):
    """No machine-route shape reads these, so the advisory family names them."""
    assert advisory_shape(value) == shape
    assert route_shape(value) is None


@pytest.mark.parametrize("value", ADVISORY_PROBE_VALUES, ids=ADVISORY_PROBE_IDS)
def test_no_boundary_keeps_a_refusal_for_an_advisory_shape(value, tmp_path):
    """The label is a label. No boundary refuses because a shape here was read."""
    assert not aggregate_refuses(value)
    assert gate_refusal_reason(value) is not PrivacyRefusalReason.LOCAL_PATH
    assert not tracker_refuses(value)
    assert not scan_refuses(value, tmp_path, name="guide.md")
    assert tracker_admits(value)


def test_the_record_admits_every_advisory_probe_outright():
    """Two of the three also cross a fault packet whole.

    The third meets the gate's own older rule against a written value, which
    reads a quotation mark and an equals sign and no shape of this family. That
    rule is the packet's, not the locator's, and the record admits all three.
    """
    for value in ADVISORY_PROBE_VALUES:
        assert not aggregate_refuses(value)
        assert tracker_admits(value)
    assert gate_refusal_reason(BARE_STORE_ADDRESS) is None
    assert gate_refusal_reason(BARE_HOST_AND_PORT) is None
    assert gate_refusal_reason(WRITTEN_CONNECTION_STRING) is PrivacyRefusalReason.SINGLETON_VALUE


@pytest.mark.parametrize("value", BENIGN_VALUES, ids=BENIGN_IDS)
def test_a_benign_declared_value_is_admitted_everywhere_and_warns_nowhere(value):
    """A column range and a rate are ordinary; neither is refused nor labelled."""
    assert not aggregate_refuses(value)
    assert gate_refusal_reason(value) is None
    assert tracker_admits(value)
    assert advisory_shape(value) is None


@pytest.mark.parametrize(
    ("shape", "benign", "route"),
    [(shape, benign, route) for _, shape, benign, route in NARROWED_SHAPES],
    ids=NARROWED_IDS,
)
def test_a_narrowed_shape_admits_the_benign_value_and_still_reads_its_route(shape, benign, route):
    """Each narrowing gives up one reading and keeps the route it was written for."""
    assert route_shape(benign) is None
    assert route_shape(route) == shape
    for boundary in (aggregate_refuses, gate_refuses, tracker_refuses):
        assert boundary(route)


# --- Every documented refusal clause, bound at the record ---


def test_both_released_sentences_list_exactly_the_clauses_the_owner_has_shapes_for():
    """A clause without a matching shape, or a shape without a clause, fails here."""
    declared = tuple(dict.fromkeys(clause for clause, _, _ in REFUSED_CLAUSES))
    for relative in RELEASED_SURFACES:
        assert released_refusal_clauses(relative) == declared, relative
        text = (ROOT / relative).read_text(encoding="utf-8").lower()
        for clause in WARNED_CLAUSES:
            assert clause in text, relative
    assert {shape for _, _, shape in REFUSED_CLAUSES} == set(owner.MACHINE_ROUTE_SHAPES)
    assert {shape for _, _, shape in ADVISORY_PROBES} == set(owner.ADVISORY_SHAPES)


@pytest.mark.parametrize(
    ("value", "shape"),
    [(value, shape) for _, value, shape in REFUSED_CLAUSES],
    ids=CLAUSE_IDS,
)
def test_each_refusal_clause_of_the_released_sentence_is_refused_at_the_record(value, shape):
    """Each refused shape keeps an error of its own, naming what it read."""
    assert route_shape(value) == shape
    assert aggregate_refusal(value) == f"locator position must be logical, not a {shape}"


# --- The seen-RED proof for each shape this correction added ---


@pytest.mark.parametrize(
    ("shape", "value"),
    [(shape, value) for _, shape, value in RESTORED_SHAPE_PROBES],
    ids=RESTORED_SHAPE_IDS,
)
def test_removing_a_restored_shape_admits_the_probe_it_alone_catches(shape, value):
    """Each added shape is load-bearing: without it the probe crosses again."""
    without = tuple(name for name in owner.MACHINE_ROUTE_SHAPES if name != shape)
    full = owner.shapes(owner.MACHINE_ROUTE_PATTERNS, owner.MACHINE_ROUTE_SHAPES)

    assert owner.shape_carried(owner.shapes(owner.MACHINE_ROUTE_PATTERNS, without), value) is None
    assert owner.shape_carried(full, value) == shape


@pytest.mark.parametrize(
    ("shape", "value"),
    [(shape, value) for _, value, shape in ADVISORY_PROBES],
    ids=ADVISORY_PROBE_IDS,
)
def test_removing_an_advisory_shape_loses_the_warning_it_alone_carries(shape, value):
    """Each advisory shape is load-bearing: without it the probe is labelled by none."""
    without = tuple(name for name in owner.ADVISORY_SHAPES if name != shape)

    assert owner.shape_carried(owner.shapes(owner.ADVISORY_PATTERNS, without), value) is None
    assert advisory_shape(value) == shape


# --- One owner, proved by the pattern objects themselves ---


def test_every_boundary_reads_the_owner_s_own_pattern_objects():
    declared = set(map(id, owner.MACHINE_ROUTE_PATTERNS.values()))
    for read in (LOCAL_PATH_PATTERNS, pinax.MACHINE_ROUTES):
        assert {id(pattern) for _, pattern in read} <= declared
    assert {id(pattern) for _, pattern in public_boundary.LOCAL_PATTERNS} - declared == {
        id(dict(public_boundary.LOCAL_PATTERNS)["private operational record"])
    }
    credentials = set(map(id, owner.CREDENTIAL_PATTERNS.values()))
    for read in (GATE_CREDENTIALS, INTAKE_CREDENTIALS):
        assert {id(pattern) for _, pattern in read} <= credentials
    assert {id(pattern) for _, pattern in RAW_ROW_PATTERNS} <= set(
        map(id, owner.RAW_ROW_PATTERNS.values())
    )
    assert {id(pattern) for _, pattern in LOCATOR_ADVISORY_SHAPES} <= set(
        map(id, owner.ADVISORY_PATTERNS.values())
    )


def test_each_boundary_reads_the_shapes_its_subject_allows():
    """Every selection is a named subset of the owner's families, never a new shape."""
    assert [name for name, _ in LOCAL_PATH_PATTERNS] == list(owner.MACHINE_ROUTE_SHAPES)
    assert [name for name, _ in pinax.MACHINE_ROUTES] == list(owner.MACHINE_ROUTE_SHAPES)
    assert list(public_boundary.SCANNED_SHAPES) == [
        name
        for name in owner.MACHINE_ROUTE_SHAPES
        if name not in public_boundary.UNREAD_SHAPES
    ]
    assert [name for name, _ in GATE_CREDENTIALS] == list(owner.CREDENTIAL_SHAPES)
    assert [name for name, _ in INTAKE_CREDENTIALS] == [
        owner.ASSIGNED_SECRET,
        owner.KEY_BLOCK,
        owner.CONNECTION_CREDENTIAL,
        owner.BEARER_AUTHORIZATION,
    ]
    # The one boundary that reads the advisory family reads all of it, and it is
    # the only one: nothing else in the product reads a shape for a warning.
    assert [name for name, _ in LOCATOR_ADVISORY_SHAPES] == list(owner.ADVISORY_SHAPES)


def test_the_tracker_s_note_form_is_the_owner_s_composed_reference():
    """One composed form, so a gap note and the scan's allowance cannot drift apart."""
    assert pinax.NOTE_SCHEME == owner.LOGICAL_REFERENCE_FORM
    assert owner.LOGICAL_REFERENCE_FORM in owner.ALLOWED_SCHEME_FORMS
    assert owner.LOGICAL_REFERENCE_FORM.startswith(owner.LOGICAL_REFERENCE_SCHEME)


def test_an_unowned_shape_name_cannot_be_read_by_a_boundary():
    with pytest.raises(KeyError):
        owner.shapes(owner.MACHINE_ROUTE_PATTERNS, ("a shape nobody owns",))


# --- No module outside the owner compiles a shape of these three families ---

# Every compiled pattern the product holds, named, with what it is. A pattern
# of one of the three families belongs to the owner and to nobody else. Every
# other entry is a pattern over something that is not a machine route, a
# credential or a raw row, and the note says what.
COMPILED_PATTERNS: dict[str, dict[str, int]] = {
    # The owner. The three closed families, and nothing else.
    "boundary_patterns.py": {
        "MACHINE_ROUTE_PATTERNS": 13,
        "CREDENTIAL_PATTERNS": 7,
        "RAW_ROW_PATTERNS": 3,
        "ADVISORY_PATTERNS": 2,
    },
    # A readable record's field lines, and one segment of a repository path.
    "composition.py": {"RECORD_LINE": 1, "PATH_SEGMENT": 1},
    # A plain identity in a tracker reference, and an actor's role and host.
    "delivery/pinax.py": {"REFERENCE_SEGMENT": 1, "ACTOR_HANDLE": 1},
    # A generator reference and a heading in a validated Koine projection.
    "koine_projection.py": {"GENERATOR_REFERENCE": 1, "SECTION_HEADING": 1},
    # The private operational record names, and the token the leakage policy
    # hashes. Neither is a route, a credential or a row.
    "public_boundary.py": {"LOCAL_PATTERNS": 1, "TOKEN": 1},
    # A pointer from one runtime adapter to the material it loads.
    "runtime_adapters.py": {"POINTER": 1},
    # A written observation of one subject, and an opaque fingerprint. Neither
    # is read by any other boundary, so both stay with the rule that refuses
    # them.
    "verification/enforcement/privacy.py": {"VALUE_LITERAL_PATTERNS": 4, "FINGERPRINT": 1},
}


def compiled_pattern_sites(source: str) -> dict[str, int]:
    """Name every compiled pattern one module holds, and how many each name binds."""
    tree = ast.parse(source)
    sites: dict[str, int] = {}
    assigned = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None:
            continue
        compiled = sum(1 for child in ast.walk(value) if is_compile_call(child))
        if not compiled:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        name = getattr(targets[0], "id", "<unnamed>")
        sites[name] = sites.get(name, 0) + compiled
        assigned += compiled
    total = sum(1 for node in ast.walk(tree) if is_compile_call(node))
    if total != assigned:
        sites["<unnamed>"] = sites.get("<unnamed>", 0) + total - assigned
    return sites


def is_compile_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compile"
    )


def product_compiled_patterns(root: Path) -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    for path in sorted(root.rglob("*.py")):
        sites = compiled_pattern_sites(path.read_text(encoding="utf-8"))
        if sites:
            found[path.relative_to(root).as_posix()] = sites
    return found


def test_every_compiled_pattern_in_the_product_is_named_and_dispositioned():
    assert product_compiled_patterns(SOURCE_ROOT) == COMPILED_PATTERNS


def test_only_the_owner_holds_the_four_families():
    held = COMPILED_PATTERNS["boundary_patterns.py"]

    assert sum(held.values()) == len(owner.MACHINE_ROUTE_PATTERNS) + len(
        owner.CREDENTIAL_PATTERNS
    ) + len(owner.RAW_ROW_PATTERNS) + len(owner.ADVISORY_PATTERNS)
    assert set(held) == {
        "MACHINE_ROUTE_PATTERNS",
        "CREDENTIAL_PATTERNS",
        "RAW_ROW_PATTERNS",
        "ADVISORY_PATTERNS",
    }


def test_a_pattern_compiled_outside_the_owner_reddens_the_inventory(tmp_path):
    """The seen-RED proof: a new compiled shape anywhere reddens until it is named."""
    mirror = tmp_path / "evorthon_data"
    mirror.mkdir()
    (mirror / "koine_session.py").write_text(
        "import re" + chr(10) + "SMUGGLED = re.compile('estate')" + chr(10), encoding="utf-8"
    )

    assert product_compiled_patterns(mirror) == {"koine_session.py": {"SMUGGLED": 1}}
    assert product_compiled_patterns(mirror) != COMPILED_PATTERNS


def test_the_owner_carries_no_route_of_its_own(tmp_path):
    """The owner ships in the public candidate, so the scan reads it and finds nothing."""
    copied = tmp_path / OWNER_MODULE.name
    copied.write_text(OWNER_MODULE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / public_boundary.POLICY).write_text(
        json.dumps({"forbidden_token_hashes": []}), encoding="utf-8"
    )

    assert scan_candidate(tmp_path) == []
