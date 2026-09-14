"""Repository diagnostics, the use-case routes and the verification routes.

Every route parses words, asks the composition root to compose the values those
words declare, and writes down what the root reported. It decides nothing: no
readiness rule, no lifecycle rule, no record rule, no delivery rule and no
verification rule is stated here. The verification routes take logical adapter
identities and never a path, and every value they report is one a verification
workflow decided and the verification presentation surface wrote down.

The output convention, which later command surfaces adopt unchanged:

- Envelope. With the json option a route writes one JSON object on one line to
  standard output, with keys in code-point order, no spaces between members,
  printable ASCII only, and a closing line feed. Every envelope carries "form"
  (the convention name), "command" (the route), "status" ("ok" or "refused")
  and "exit code". A completed route carries "result", an object of the values
  the route reported; a route that read readiness also carries "segments",
  "gaps" and "open conditions" inside it. A refused route carries "error"
  instead of "result".
- Exit codes. 0 when the route completed, 2 when the command line could not be
  parsed, and 3 when the route refused. No other code is returned. The parser
  leaves through the same table, so an unparsable command line and a refused
  route never share a code.
- Error shape. "error" is an object of exactly two members: "reason", one word
  from the closed set of integrity reasons the composition root declares, and
  "detail", one sentence naming what was refused.

Without the json option a route writes concise human lines to standard output,
one value per line, and a refusal to standard error as a single line opening
with the word refused.

Values are given as plain text. A value that carries more than one field is
written as its fields separated by a colon, in the order its field table
states, and the last field takes whatever remains. A repeated option is given
once per entry. A declared field of a recorded fact is written as its field
name, an equals sign, and its value; the composition root names the fields each
declaration kind holds.
"""
# evorthon-implements: EVD-README-034
# evorthon-component: presentation
import argparse
import json
import sys

from . import composition
from .composition import CompositionError
from .dependencies import installed_capabilities
from .presentation.use_case import (
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_USAGE,
    envelope,
    refusal_envelope,
    refusal_line,
    result_lines,
    written,
)

PRODUCT = "evorthon-data-harness"
DIAGNOSE = "diagnose"
USE_CASE = "use-case"
VERIFICATION = "verification"
DEFAULT_REPOSITORY = "."
DEFAULT_RECORDS_ROOT = "work"
DEFAULT_PREFIX = "evd"


class CommandParser(argparse.ArgumentParser):
    """The command parser, leaving through the exit code the convention declares."""

    def error(self, message: str):
        """Report an unparsable command line and leave with the usage code."""
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv=None):
    """Run one command and return the exit code the convention declares."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        arguments = [DIAGNOSE]
    parsed = build_parser().parse_args(arguments)
    if parsed.command == DIAGNOSE:
        print(json.dumps({"product": PRODUCT, "capabilities": installed_capabilities()}, sort_keys=True))
        return EXIT_OK
    return run_route(parsed)


def run_route(parsed) -> int:
    """Drive one use-case route and report what the composition root returned."""
    command = f"{parsed.command} {parsed.route}"
    try:
        result = ROUTE_TABLES[parsed.command][parsed.route](parsed)
    except CompositionError as refusal:
        if parsed.json:
            print(written(refusal_envelope(command, refusal.reason.value, refusal.detail)))
        else:
            print(refusal_line(refusal.reason.value, refusal.detail), file=sys.stderr)
        return EXIT_REFUSED
    if parsed.json:
        print(written(envelope(result)))
    else:
        for line in result_lines(result):
            print(line)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """Build the whole command surface, one parser per route."""
    parser = CommandParser(prog=PRODUCT, description="Evorthon Data Harness command routes")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(DIAGNOSE, help="report the installed delivery capabilities")
    routes = commands.add_parser(USE_CASE, help="open, record, read and accept a use case")
    declared = routes.add_subparsers(dest="route", required=True)

    opened = _route(declared, "open", "open a use case and hold it in a new record")
    opened.add_argument("--engagement", required=True, help="the engagement identity")
    opened.add_argument("--use-case", required=True, help="the use case identity")
    opened.add_argument("--use-case-version", required=True, help="the use case identity version")
    opened.add_argument("--use-case-digest", required=True, help="the use case identity digest")
    opened.add_argument("--mode", required=True, help="the engagement mode")
    opened.add_argument("--consumer", required=True, help="who consumes the outcome")
    opened.add_argument("--outcome", required=True, help="the consumer outcome")
    opened.add_argument("--done-definition", required=True, help="what done means")
    opened.add_argument("--cadence", required=True, help="how often the outcome is needed")
    opened.add_argument("--deadline", required=True, help="when the outcome is needed by")
    opened.add_argument("--provenance", required=True, help="the provenance behind the header facts")

    recorded = _held(declared, "record-fact", "record one declaration on a held use case")
    recorded.add_argument(
        "--kind", required=True, choices=list(composition.DECLARATION_KINDS), help="the declaration kind"
    )
    recorded.add_argument(
        "--field", action="append", default=[], help="one declared field, written as name=value"
    )

    read = _held(declared, "readiness", "report the readiness of a held use case")
    _case_options(read)

    generated = _reported(declared, "synthesise-dataset", "generate one labelled synthetic dataset")
    generated.add_argument("--request", required=True, help="the constraint request document")
    generated.add_argument("--seed", required=True, help="the generation seed")
    generated.add_argument("--generator-version", required=True, help="the generator version")

    cut = _held(declared, "cut-version", "cut one version on a recomputed readiness projection")
    cut.add_argument("--version", required=True, help="the version identity")
    cut.add_argument("--version-version", required=True, help="the version identity version")
    cut.add_argument("--version-digest", required=True, help="the version identity digest")
    cut.add_argument("--projection", required=True, help="the projection identity")
    cut.add_argument("--projection-version", required=True, help="the projection identity version")
    cut.add_argument("--readiness-digest", required=True, help="the digest the cut is stated on")
    cut.add_argument("--covered-segment", action="append", default=[], help="one covered span")
    cut.add_argument("--scenario-case", action="append", default=[], help="one scenario case version")
    cut.add_argument("--package", action="append", default=[], help="one approved package identity")
    cut.add_argument("--evidence", action="append", default=[], help="one evidence identity")
    _case_options(cut)

    accepted = _held(declared, "record-acceptance", "record one named human acceptance")
    accepted.add_argument("--version", required=True, help="the version identity being accepted")
    accepted.add_argument("--decision", required=True, help="the decision identity")
    accepted.add_argument("--decided-by", required=True, help="the accepting authority")
    accepted.add_argument("--rationale", required=True, help="the decision rationale identity")
    accepted.add_argument("--case-reading", action="append", default=[], help="one case evidence reading")
    _case_options(accepted)

    projected = _held(declared, "project-gaps", "project the readiness gaps as tracked work")
    projected.add_argument("--actor", required=True, help="the tracker actor handle")
    projected.add_argument("--prefix", default=DEFAULT_PREFIX, help="the tracker item prefix")
    projected.add_argument("--tracker-repository", default=None, help="the tracker repository")
    _case_options(projected)

    verification = commands.add_parser(
        VERIFICATION, help="take in, verify and diagnose one approved verification case"
    )
    cases = verification.add_subparsers(dest="route", required=True)

    _case_route(cases, "intake-case", "read one approved case and take it in read-only")
    verified = _case_route(cases, "verify", "verify one accepted case against its whole contract")
    _material_option(verified)
    diagnosed = _case_route(
        cases, "diagnose-failure", "diagnose one output a recorded outcome reports as failing"
    )
    _material_option(diagnosed)
    diagnosed.add_argument("--output", required=True, help="the output the diagnosis answers for")

    remediated = _case_document_route(
        cases, "record-remediation", "record one named human disposition of one piece of advice"
    )
    _disposition_options(remediated)
    remediated.add_argument(
        "--use-case", default=None, help="the use case the tracked work sits under"
    )
    remediated.add_argument("--actor", default=None, help="the tracker actor handle")
    remediated.add_argument("--prefix", default=DEFAULT_PREFIX, help="the tracker item prefix")
    remediated.add_argument("--tracker-repository", default=None, help="the tracker repository")
    remediated.add_argument(
        "--iteration",
        default=None,
        help="the iteration the remedy corrects, as its identity, its span and its summary",
    )
    remediated.add_argument(
        "--remedy-summary", default=None, help="the summary the tracked remedy carries"
    )
    _case_options(remediated)

    rerun = _case_route(
        cases, "rerun", "rerun one corrected candidate over the case a decision cites"
    )
    _disposition_options(rerun)
    rerun.add_argument("--decision", required=True, help="the recorded decision the rerun runs for")
    _material_option(rerun)
    rerun.add_argument(
        "--prior-candidate-adapter",
        required=True,
        help="the logical identity of the candidate the recorded outcome was taken over",
    )
    rerun.add_argument(
        "--prior-material",
        required=True,
        help="the material document the recorded outcome was taken over",
    )

    _case_document_route(
        cases, "acceptance-evidence", "report what a named human acceptance would rest on"
    )
    return parser


def _case_document_route(declared, name: str, help_text: str) -> argparse.ArgumentParser:
    parser = _route(declared, name, help_text)
    parser.add_argument("--engagement", required=True, help="the engagement identity")
    parser.add_argument(
        "--case", required=True, help="the case document, named under the records root"
    )
    return parser


def _case_route(declared, name: str, help_text: str) -> argparse.ArgumentParser:
    parser = _case_document_route(declared, name, help_text)
    parser.add_argument(
        "--evidence-adapter", required=True, help="the logical identity of the evidence adapter"
    )
    parser.add_argument(
        "--candidate-adapter", required=True, help="the logical identity of the candidate adapter"
    )
    return parser


def _disposition_options(parser: argparse.ArgumentParser) -> None:
    """Declare the words and documents one named human disposition is given in."""
    parser.add_argument(
        "--advice", required=True, help="the advice document, named under the records root"
    )
    parser.add_argument(
        "--disposition",
        required=True,
        choices=list(composition.HUMAN_DISPOSITION_WORDS),
        help="the disposition a named human took",
    )
    parser.add_argument(
        "--decided-by",
        required=True,
        help="the deciding actor, written as its identity and then the kind of actor it is",
    )
    parser.add_argument(
        "--rationale", required=True, help="the rationale document, named under the records root"
    )
    parser.add_argument(
        "--requested-evidence",
        action="append",
        default=[],
        help="one thing an evidence request asks for",
    )
    parser.add_argument(
        "--edited-remedy", default=None, help="the remedy document a modified disposition carries"
    )
    parser.add_argument(
        "--owner-presented", default=None, help="the owner-presented evidence document presented"
    )
    parser.add_argument(
        "--certificate", default=None, help="the environment certificate document presented"
    )
    return None


def _material_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--material", required=True, help="the material document, named under the records root"
    )
    return None


def _reported(declared, name: str, help_text: str) -> argparse.ArgumentParser:
    parser = declared.add_parser(name, help=help_text)
    parser.add_argument("--json", action="store_true", help="write the machine envelope")
    return parser


def _route(declared, name: str, help_text: str) -> argparse.ArgumentParser:
    parser = _reported(declared, name, help_text)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY, help="the repository root")
    parser.add_argument(
        "--records-root", default=DEFAULT_RECORDS_ROOT, help="the records root inside the work directory"
    )
    return parser


def _held(declared, name: str, help_text: str) -> argparse.ArgumentParser:
    parser = _route(declared, name, help_text)
    parser.add_argument("--engagement", required=True, help="the engagement identity")
    parser.add_argument("--use-case", required=True, help="the use case identity")
    return parser


def _case_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case-dataset", action="append", default=[], help="one case dataset fact")
    parser.add_argument(
        "--case-expected-output", action="append", default=[], help="one case expected output fact"
    )
    parser.add_argument("--case-checkpoint", action="append", default=[], help="one case checkpoint fact")
    parser.add_argument("--case-status", action="append", default=[], help="one case result status")
    return None


def _case_facts(parsed) -> dict[str, tuple[str, ...]]:
    return {
        "case_datasets": tuple(parsed.case_dataset),
        "case_expected_outputs": tuple(parsed.case_expected_output),
        "case_checkpoints": tuple(parsed.case_checkpoint),
        "case_statuses": tuple(parsed.case_status),
    }


def _open(parsed):
    identity = composition.compound(
        (parsed.use_case, parsed.use_case_version, parsed.use_case_digest), "a use case reference"
    )
    return composition.open_use_case(
        repository=parsed.repository,
        root=parsed.records_root,
        header_parts=(
            identity,
            parsed.engagement,
            parsed.mode,
            parsed.consumer,
            parsed.outcome,
            parsed.done_definition,
            parsed.cadence,
            parsed.deadline,
            parsed.provenance,
        ),
    )


def _record_fact(parsed):
    return composition.record_fact(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        use_case_id=parsed.use_case,
        kind=parsed.kind,
        declared_fields=tuple(parsed.field),
    )


def _readiness(parsed):
    return composition.read_use_case_readiness(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        use_case_id=parsed.use_case,
        **_case_facts(parsed),
    )


def _synthesise_dataset(parsed):
    return composition.synthesise_dataset(
        document=composition.read_document(parsed.request),
        seed=parsed.seed,
        generator_version=parsed.generator_version,
    )


def _cut_version(parsed):
    return composition.cut_use_case_version(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        use_case_id=parsed.use_case,
        version_reference=composition.compound(
            (parsed.version, parsed.version_version, parsed.version_digest), "a version reference"
        ),
        covered_segments=composition.list_part(parsed.covered_segment, "a covered span"),
        projection_reference=composition.compound(
            (parsed.projection, parsed.projection_version), "a projection reference"
        ),
        readiness_digest=parsed.readiness_digest,
        scenario_case_versions=composition.list_part(parsed.scenario_case, "a scenario case version"),
        packages=composition.list_part(parsed.package, "a package"),
        evidence=composition.list_part(parsed.evidence, "an evidence identity"),
        **_case_facts(parsed),
    )


def _record_acceptance(parsed):
    return composition.record_use_case_acceptance(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        use_case_id=parsed.use_case,
        version_identity=parsed.version,
        decision_identity=parsed.decision,
        decided_by=parsed.decided_by,
        rationale=parsed.rationale,
        case_readings=composition.list_part(parsed.case_reading, "a case reading"),
        **_case_facts(parsed),
    )


def _project_gaps(parsed):
    return composition.project_use_case_gaps(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        use_case_id=parsed.use_case,
        actor_handle=parsed.actor,
        prefix=parsed.prefix,
        tracker_repository=parsed.tracker_repository,
        **_case_facts(parsed),
    )


def _intake_case(parsed):
    return composition.intake_verification_case(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        case_document=parsed.case,
        evidence_identity=parsed.evidence_adapter,
        candidate_identity=parsed.candidate_adapter,
    )


def _verify(parsed):
    return composition.verify_case(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        case_document=parsed.case,
        material_document=parsed.material,
        evidence_identity=parsed.evidence_adapter,
        candidate_identity=parsed.candidate_adapter,
    )


def _diagnose_failure(parsed):
    return composition.diagnose_case_failure(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        case_document=parsed.case,
        material_document=parsed.material,
        evidence_identity=parsed.evidence_adapter,
        candidate_identity=parsed.candidate_adapter,
        output_id=parsed.output,
    )


def _disposition(parsed) -> dict[str, object]:
    """The words and documents one disposition is declared by, exactly as given."""
    return {
        "advice_document": parsed.advice,
        "disposition": parsed.disposition,
        "decided_by": parsed.decided_by,
        "rationale_document": parsed.rationale,
        "requested_evidence": tuple(parsed.requested_evidence),
        "remedy_document": parsed.edited_remedy,
        "owner_document": parsed.owner_presented,
        "certificate_document": parsed.certificate,
    }


def _record_remediation(parsed):
    return composition.record_remediation(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        case_document=parsed.case,
        use_case_id=parsed.use_case,
        actor_handle=parsed.actor,
        prefix=parsed.prefix,
        tracker_repository=parsed.tracker_repository,
        iteration=parsed.iteration,
        remedy_summary=parsed.remedy_summary,
        **_disposition(parsed),
        **_case_facts(parsed),
    )


def _rerun(parsed):
    return composition.rerun_remediation(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        case_document=parsed.case,
        decision_identity=parsed.decision,
        evidence_identity=parsed.evidence_adapter,
        candidate_identity=parsed.candidate_adapter,
        material_document=parsed.material,
        prior_candidate_identity=parsed.prior_candidate_adapter,
        prior_material_document=parsed.prior_material,
        **_disposition(parsed),
    )


def _acceptance_evidence(parsed):
    return composition.read_acceptance_evidence(
        repository=parsed.repository,
        root=parsed.records_root,
        engagement_id=parsed.engagement,
        case_document=parsed.case,
    )


ROUTES = {
    "open": _open,
    "record-fact": _record_fact,
    "readiness": _readiness,
    "synthesise-dataset": _synthesise_dataset,
    "cut-version": _cut_version,
    "record-acceptance": _record_acceptance,
    "project-gaps": _project_gaps,
}

# The verification routes, held apart from the use-case routes because each
# command group owns the routes it declares.
VERIFICATION_ROUTES = {
    "intake-case": _intake_case,
    "verify": _verify,
    "diagnose-failure": _diagnose_failure,
    "record-remediation": _record_remediation,
    "rerun": _rerun,
    "acceptance-evidence": _acceptance_evidence,
}

# The one table a command group is driven through.
ROUTE_TABLES = {USE_CASE: ROUTES, VERIFICATION: VERIFICATION_ROUTES}


if __name__ == "__main__":
    raise SystemExit(main())
