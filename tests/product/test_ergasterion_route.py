"""Hermetic proofs for the Ergasterion generation route and its lineage mapping."""
# evorthon-verifies: EVD-README-016
# evorthon-verifies: EVD-README-008
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
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
from evorthon_data.verification.domain import (
    CanonicalisationDeclaration,
    Identity,
    OutputLineageBinding,
    SchemaValueType,
)

ROOT = Path(__file__).parents[2]
DELIVERY_TOOL_ROOTS = {
    "ergasterion",
    "ergasterion_factory",
    "autobuild",
    "autobuild_factory",
    "pinax",
    "pinax_tracker",
}
RETIRED_COMMAND_NAMES = {"emit", "evolve", "graph"}

HELP_TEXT = (
    "usage: ergasterion <subcommand> [args...]\n"
    "\n"
    "subcommands: emit-products, contracts, product-graph, lint, structure, init, validate\n"
)

NODE_TABLE = (
    "id,name,domain,layer,profile,shape,generation,relations,materialisation,checkpoint\n"
    "risk.settled_positions,settled_positions,risk,derived,derivation,declared,first,"
    "risk.settled_positions,table,true\n"
    "risk.exposure_summary,exposure_summary,risk,derived,derivation,declared,later,"
    "risk.exposure_summary,undeclared,false\n"
)
EDGE_TABLE = (
    "edge_id,src,dst,kind,contract,relation\n"
    "e00001,risk.settled_positions,risk.exposure_summary,source,risk.settled_positions@1,"
    "risk.settled_positions\n"
)
FIELD_LINEAGE_TABLE = (
    "edge_id,product,target_field,source_kind,source_product,source,occurrence,transform\n"
    "f00001,risk.settled_positions,booked_on,field,risk.settled_positions,booked_at,"
    "steps[2]:calculated_fields,calculated_fields\n"
    "f00002,risk.exposure_summary,exposure_label,expression,risk.exposure_summary,constant,"
    "steps[2]:calculated_fields,calculated_fields\n"
)
GRAPH_DESCRIPTION = {
    "auxiliary_relations": [
        {
            "product": "risk.settled_positions",
            "relation": "risk.settled_positions__spine",
            "translator": "dbt",
            "purpose": "shared time spine",
        }
    ],
    "checkpoint_relations": ["risk.settled_positions"],
    "counts": {
        "declared_fields": 2,
        "edges": 1,
        "field_lineage": 2,
        "products": 2,
        "validations": 2,
    },
    "generations": {
        "consolidating": [],
        "first": ["risk.settled_positions"],
        "landing": [],
        "later": ["risk.exposure_summary"],
    },
    "order": ["risk.settled_positions", "risk.exposure_summary"],
    "relations": {
        "risk.exposure_summary": ["risk.exposure_summary"],
        "risk.settled_positions": ["risk.settled_positions"],
    },
    "schema": "ergasterion.product-graph/v1",
}
PRODUCER_CONTRACT = {
    "identity": {"domain": "risk", "major": 1, "name": "settled_positions", "namespace": "com.example"},
    "relations": [
        {
            "fields": [
                {"name": "position_id", "required": True, "type": "string"},
                {"name": "booked_at", "required": False, "type": "timestamp"},
                {"name": "booked_on", "required": False, "type": "date"},
                {
                    "name": "exposure_amount",
                    "required": False,
                    "type": {"name": "decimal", "precision": 18, "scale": 2},
                },
            ],
            "name": "risk.settled_positions",
        }
    ],
    "schema": "ergasterion.product-contract/v1",
}
CONSUMER_CONTRACT = {
    "identity": {"domain": "risk", "major": 1, "name": "exposure_summary", "namespace": "com.example"},
    "relations": [
        {
            "fields": [
                {"name": "position_id", "required": True, "type": "string"},
                {"name": "exposure_label", "required": False, "type": "string"},
            ],
            "name": "risk.exposure_summary",
        }
    ],
    "schema": "ergasterion.product-contract/v1",
}
PRODUCER_MANIFEST = {
    "materialisation": {"intent": "table", "publication_mode": "atomic", "unique_key": ["position_id"]},
    "product": "risk.settled_positions",
    "schema": "ergasterion.product-runtime/v1",
}
CONSUMER_MANIFEST = {
    "materialisation": {"intent": "undeclared", "publication_mode": "atomic", "unique_key": []},
    "product": "risk.exposure_summary",
    "schema": "ergasterion.product-runtime/v1",
}


def document(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def recorded_estate() -> dict[str, str]:
    """The generated artefacts of one emitted estate, recorded as text."""
    return {
        "graphs/products/product-graph.json": document(GRAPH_DESCRIPTION),
        "graphs/products/product-nodes.csv": NODE_TABLE,
        "graphs/products/product-edges.csv": EDGE_TABLE,
        "graphs/products/product-field-lineage.csv": FIELD_LINEAGE_TABLE,
        "contracts/products/risk/settled_positions/contract.json": document(PRODUCER_CONTRACT),
        "contracts/products/risk/exposure_summary/contract.json": document(CONSUMER_CONTRACT),
        "manifests/products/risk/settled_positions.json": document(PRODUCER_MANIFEST),
        "manifests/products/risk/exposure_summary.json": document(CONSUMER_MANIFEST),
    }


@dataclass
class FakeErgasterionRunner:
    """Answer the public commands the route drives, without the released tool."""

    files: dict[str, str] = field(default_factory=recorded_estate)
    binary: dict[str, bytes] = field(default_factory=dict)
    help_text: object = HELP_TEXT
    scaffold_mode: str = "estate"
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(self, arguments, *, working_directory):
        recorded = tuple(arguments)
        self.calls.append(recorded)
        if recorded == ("--help",):
            return self.help_text
        if recorded[0] == "init":
            self._scaffold(Path(recorded[1]))
            return "scaffolded an estate"
        estate = Path(recorded[-1])
        if recorded[0] == "emit-products" and "--check" not in recorded:
            for relative, text in self.files.items():
                path = estate / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
            for relative, data in self.binary.items():
                (estate / relative).write_bytes(data)
        return f"{recorded[0]} OK"

    def _scaffold(self, estate: Path) -> None:
        if self.scaffold_mode == "empty":
            estate.mkdir(parents=True)
            return
        declarations = estate / "declarations/products"
        declarations.mkdir(parents=True)
        (estate / "seeds").mkdir(parents=True)
        if self.scaffold_mode == "nested":
            (declarations / "held").mkdir()
            return
        (declarations / "orders_summary.yml").write_text("# scaffold seed\n", encoding="utf-8")


CAPABILITIES = {"ergasterion-factory": {"installed": True, "version": "0.6.1"}}
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
DECLARATION_DOCUMENT = (
    "product:\n"
    "  name: settled_positions\n"
    "  domain: risk\n"
    "  version: \"1.0\"\n"
    "  layer: derived\n"
    "  owner: platform-team\n"
)


def contract(**overrides) -> ExactGenerationContract:
    values = {
        "identity": Identity(
            identifier="risk-settlement-generation",
            version="v1",
            digest="sha256:approved-generation-digest",
        ),
        "declarations": (ProductDeclaration("settled_positions.yml", DECLARATION_DOCUMENT),),
        "seeds": (FixtureSeed("raw_risk_position_feed.csv", "position_id,booked_at\np-1,2026-01-01\n"),),
        "canonicalisation": CANONICALISATION,
    }
    values.update(overrides)
    return ExactGenerationContract(**values)


def route(runner: FakeErgasterionRunner) -> ErgasterionGenerationRoute:
    return ErgasterionGenerationRoute(runner, actor="generation-actor", capabilities=CAPABILITIES)


def generated(tmp_path: Path, runner: FakeErgasterionRunner, name: str = "estate"):
    return route(runner).generate(contract(), estate=tmp_path / name)


def test_exact_contract_drives_the_public_commands_and_leaves_declared_products(tmp_path):
    runner = FakeErgasterionRunner()
    result = generated(tmp_path, runner)
    estate = str(tmp_path / "estate")

    assert runner.calls == [
        ("--help",),
        ("init", estate),
        ("validate", "--estate-root", estate),
        ("emit-products", "--estate-root", estate),
        ("emit-products", "--check", "--estate-root", estate),
        ("product-graph", "--check", "--estate-root", estate),
        ("contracts", "--check", "--estate-root", estate),
    ]
    assert sorted(path.name for path in (tmp_path / "estate/declarations/products").iterdir()) == [
        "settled_positions.yml"
    ]
    assert (tmp_path / "estate/seeds/raw_risk_position_feed.csv").read_text(
        encoding="utf-8"
    ).startswith("position_id")
    assert result.contract_identity.identifier == "risk-settlement-generation"


def test_no_retired_command_name_is_issued(tmp_path):
    runner = FakeErgasterionRunner()
    generated(tmp_path, runner)
    issued = {call[0] for call in runner.calls} - {"--help"}

    assert issued.isdisjoint(RETIRED_COMMAND_NAMES)
    assert issued <= set(REQUIRED_COMMANDS)
    assert RETIRED_COMMAND_NAMES.isdisjoint(set(REQUIRED_COMMANDS))


def test_graph_files_map_into_the_verification_domain_lineage(tmp_path):
    runner = FakeErgasterionRunner()
    result = generated(tmp_path, runner)
    reading = result.graph

    assert [node.published_name for node in reading.nodes] == list(GRAPH_DESCRIPTION["order"])
    assert len(reading.edges) == GRAPH_DESCRIPTION["counts"]["edges"]
    assert len(reading.field_lineage) == GRAPH_DESCRIPTION["counts"]["field_lineage"]
    assert [checkpoint.checkpoint_id for checkpoint in result.lineage.checkpoints] == list(
        GRAPH_DESCRIPTION["checkpoint_relations"]
    )
    assert [entry.relation for entry in result.auxiliary_lineage] == [
        "risk.settled_positions__spine"
    ]

    checkpoint = result.lineage.checkpoints[0]
    assert checkpoint.version == "v1"
    assert checkpoint.parent_ids == ()
    assert checkpoint.grain.key_fields == ("position_id",)
    assert checkpoint.grain.duplicate_keys_permitted is False
    assert checkpoint.canonicalisation is CANONICALISATION
    assert checkpoint.transformation.identifier == "risk.settled_positions"
    assert checkpoint.provenance.identifier == "ergasterion.product-graph/v1"
    assert checkpoint.replay is None
    assert [(field_.field_id, field_.value_type, field_.semantic_role) for field_ in checkpoint.schema.fields] == [
        ("position_id", SchemaValueType.STRING, "declared"),
        ("booked_at", SchemaValueType.TIMESTAMP, "declared"),
        ("booked_on", SchemaValueType.DATE, "field"),
        ("exposure_amount", SchemaValueType.DECIMAL, "declared"),
    ]
    assert checkpoint.schema.fields[0].nullable is False
    assert (checkpoint.schema.fields[3].precision, checkpoint.schema.fields[3].scale) == (18, 2)
    assert result.lineage.output_bindings == (
        OutputLineageBinding(
            expected_output_id="risk.exposure_summary",
            terminal_checkpoint_id="risk.settled_positions",
        ),
    )


def test_repeated_generation_from_one_contract_yields_identical_digests(tmp_path):
    first = generated(tmp_path, FakeErgasterionRunner(), "first")
    second = generated(tmp_path, FakeErgasterionRunner(), "second")

    assert first.artefact_digests == second.artefact_digests
    assert dict(first.artefact_digests)["graphs/products/product-graph.json"].startswith("sha256:")
    assert len(first.artefact_digests) == len(recorded_estate())


def test_consumer_major_mismatch_is_refused_on_the_evorthon_side(tmp_path):
    files = recorded_estate()
    files["graphs/products/product-edges.csv"] = EDGE_TABLE.replace(
        "risk.settled_positions@1", "risk.settled_positions@2"
    )
    runner = FakeErgasterionRunner(files=files)

    with pytest.raises(ErgasterionRouteError, match=r"pin risk.settled_positions@2 does not match"):
        generated(tmp_path, runner)


def test_matching_consumer_major_is_accepted(tmp_path):
    result = generated(tmp_path, FakeErgasterionRunner())

    assert [edge.contract_reference for edge in result.graph.edges] == ["risk.settled_positions@1"]


def test_unsupported_capability_fails_through_the_installed_capability_report(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    from evorthon_data import dependencies

    def absent(distribution: str):
        raise PackageNotFoundError(distribution)

    monkeypatch.setattr(dependencies, "version", absent)
    capabilities = dependencies.installed_capabilities()
    runner = FakeErgasterionRunner()

    assert capabilities["ergasterion-factory"] == {"installed": False, "version": None}
    with pytest.raises(ErgasterionRouteError, match="ergasterion-factory is not installed"):
        ErgasterionGenerationRoute(
            runner, actor="generation-actor", capabilities=capabilities
        ).assert_supported()
    assert runner.calls == []


def test_missing_public_command_is_refused_by_name():
    runner = FakeErgasterionRunner(
        help_text="usage: ergasterion\n\nsubcommands: emit-products, contracts, lint, init, validate\n"
    )

    with pytest.raises(ErgasterionRouteError, match="does not support: product-graph"):
        route(runner).assert_supported()


@pytest.mark.parametrize("help_text", ["usage: ergasterion\n", None])
def test_unreadable_command_set_is_refused(help_text):
    runner = FakeErgasterionRunner(help_text=help_text)

    with pytest.raises(ErgasterionRouteError, match="command set could not be read"):
        route(runner).assert_supported()


def test_a_capability_report_is_required():
    with pytest.raises(ErgasterionRouteError, match="installed capability report is required"):
        ErgasterionGenerationRoute(
            FakeErgasterionRunner(), actor="generation-actor", capabilities=["ergasterion-factory"]
        )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"declarations": ()}, "at least one product"),
        (
            {
                "declarations": (
                    ProductDeclaration("settled_positions.yml", DECLARATION_DOCUMENT),
                    ProductDeclaration("settled_positions.yml", DECLARATION_DOCUMENT),
                )
            },
            "declare each product once",
        ),
        (
            {"declarations": (ProductDeclaration("risk/settled_positions.yml", DECLARATION_DOCUMENT),)},
            "plain .yml file name",
        ),
        (
            {"declarations": (ProductDeclaration("settled_positions.yaml", DECLARATION_DOCUMENT),)},
            "plain .yml file name",
        ),
        ({"declarations": (ProductDeclaration("settled_positions.yml", "  \n"),)}, "stated document"),
        ({"declarations": ("settled_positions.yml",)}, "stated product declaration"),
        ({"seeds": (FixtureSeed("seeds/feed.csv", "a\n1\n"),)}, "plain .csv file name"),
        ({"seeds": ["raw.csv"]}, "declare its fixture seeds"),
        ({"seeds": ("raw.csv",)}, "stated fixture seed"),
        (
            {
                "seeds": (
                    FixtureSeed("raw.csv", "a\n1\n"),
                    FixtureSeed("raw.csv", "a\n1\n"),
                )
            },
            "each fixture seed once",
        ),
        (
            {
                "identity": Identity(
                    identifier="risk-settlement-generation", version="v1", digest=""
                )
            },
            "digest is required",
        ),
        ({"canonicalisation": "NFC"}, "declare its canonicalisation"),
        (
            {
                "canonicalisation": CanonicalisationDeclaration(
                    canonicalisation_id="",
                    version="v1",
                    unicode_normalisation="NFC",
                    null_representation="empty",
                    decimal_scale=2,
                    timestamp_precision="second",
                    timezone="UTC",
                    signed_zero_representation="unsigned",
                    non_finite_number_policy="rejected",
                )
            },
            "canonicalisation identifier is required",
        ),
    ],
)
def test_inexact_generation_contracts_are_refused_with_the_reason(tmp_path, overrides, reason):
    runner = FakeErgasterionRunner()

    with pytest.raises(ErgasterionRouteError, match=reason):
        route(runner).generate(contract(**overrides), estate=tmp_path / "estate")
    assert runner.calls == []


def test_a_contract_that_is_not_an_exact_generation_declaration_is_refused(tmp_path):
    runner = FakeErgasterionRunner()

    with pytest.raises(ErgasterionRouteError, match="declares exact generation"):
        route(runner).generate({"declarations": []}, estate=tmp_path / "estate")
    assert runner.calls == []


def test_a_populated_estate_is_never_scaffolded_over(tmp_path):
    estate = tmp_path / "estate"
    estate.mkdir()
    (estate / "existing.txt").write_text("held\n", encoding="utf-8")
    runner = FakeErgasterionRunner()

    with pytest.raises(ErgasterionRouteError, match="must be an empty directory"):
        route(runner).generate(contract(), estate=estate)
    assert [call[0] for call in runner.calls] == ["--help"]


def test_a_missing_estate_parent_is_refused(tmp_path):
    runner = FakeErgasterionRunner()

    with pytest.raises(ErgasterionRouteError, match="existing parent directory"):
        route(runner).generate(contract(), estate=tmp_path / "absent/estate")
    assert [call[0] for call in runner.calls] == ["--help"]


@pytest.mark.parametrize(
    ("scaffold_mode", "reason"),
    [
        ("empty", "does not carry the declaration layout"),
        ("nested", "not a flat file set"),
    ],
)
def test_an_unusable_scaffold_is_refused_before_generation(tmp_path, scaffold_mode, reason):
    runner = FakeErgasterionRunner(scaffold_mode=scaffold_mode)

    with pytest.raises(ErgasterionRouteError, match=reason):
        generated(tmp_path, runner)
    assert [call[0] for call in runner.calls] == ["--help", "init"]


def test_an_unavailable_released_command_is_refused():
    runner = SubprocessErgasterionRunner(command=("evorthon-absent-generation-command",))

    with pytest.raises(ErgasterionRouteError, match="released Ergasterion command is unavailable"):
        runner.run(("--help",), working_directory=None)


def test_a_failing_released_command_reports_its_own_output():
    import sys

    runner = SubprocessErgasterionRunner(
        command=(sys.executable, "-c", "import sys; sys.stderr.write('declaration defect'); sys.exit(3)")
    )

    with pytest.raises(ErgasterionRouteError, match="Ergasterion command failed: declaration defect"):
        runner.run(("validate",), working_directory=None)


def without(relative: str):
    files = recorded_estate()
    del files[relative]
    return files


def without_key(key: str):
    description = {name: value for name, value in GRAPH_DESCRIPTION.items() if name != key}
    return replaced("graphs/products/product-graph.json", document(description))


def replaced(relative: str, text: str):
    files = recorded_estate()
    files[relative] = text
    return files


def described(**changes):
    description = dict(GRAPH_DESCRIPTION)
    description.update(changes)
    return replaced("graphs/products/product-graph.json", document(description))


@pytest.mark.parametrize(
    ("files", "reason"),
    [
        (without("graphs/products/product-graph.json"), "artefact is missing"),
        (without("graphs/products/product-nodes.csv"), "artefact is missing"),
        (without("graphs/products/product-edges.csv"), "artefact is missing"),
        (without("graphs/products/product-field-lineage.csv"), "artefact is missing"),
        (without("manifests/products/risk/settled_positions.json"), "artefact is missing"),
        (without("contracts/products/risk/settled_positions/contract.json"), "artefact is missing"),
        (
            {
                relative: text
                for relative, text in recorded_estate().items()
                if not relative.startswith("manifests/")
            },
            "artefact directory is missing: manifests/products",
        ),
        (replaced("graphs/products/product-graph.json", "{not json"), "is not JSON"),
        (replaced("graphs/products/product-graph.json", "[]\n"), "is not a JSON object"),
        (described(schema="ergasterion.product-graph/v0"), "does not declare its expected schema"),
        (without_key("counts"), "has no counts"),
        (described(order="risk.settled_positions"), "invalid build order"),
        (described(checkpoint_relations=["risk.settled_positions", 1]), "invalid checkpoint relation list"),
        (described(auxiliary_relations={}), "invalid auxiliary relation list"),
        (
            described(counts={"declared_fields": 2, "edges": 9, "field_lineage": 2, "products": 2}),
            "counts do not match its tables",
        ),
        (described(order=["risk.settled_positions"]), "order does not cover its nodes"),
        (
            described(relations={"risk.settled_positions": ["risk.settled_positions"]}),
            "relations do not match its nodes",
        ),
        (described(checkpoint_relations=["risk.exposure_summary"]), "checkpoint relations do not match"),
        (described(auxiliary_relations=[{"product": "risk.settled_positions"}]), "invalid auxiliary relation"),
        (
            replaced("graphs/products/product-nodes.csv", NODE_TABLE.replace("id,name", "key,name", 1)),
            "does not carry its declared header",
        ),
        (
            replaced("graphs/products/product-nodes.csv", NODE_TABLE.replace(",table,true", ",table,yes")),
            "invalid flag",
        ),
        (
            replaced("graphs/products/product-nodes.csv", NODE_TABLE + "risk.orphan,orphan\n"),
            "row does not match its header",
        ),
        (
            replaced(
                "graphs/products/product-edges.csv",
                EDGE_TABLE.replace("e00001,risk.settled_positions", "e00001,risk.unknown"),
            ),
            "edge outside its nodes",
        ),
        (
            replaced(
                "graphs/products/product-edges.csv",
                EDGE_TABLE.replace("risk.settled_positions@1", "risk.settled_positions"),
            ),
            "unreadable consumer pin",
        ),
        (
            replaced(
                "contracts/products/risk/settled_positions/contract.json",
                document(
                    {
                        **PRODUCER_CONTRACT,
                        "relations": [{**PRODUCER_CONTRACT["relations"][0], "name": "risk.other"}],
                    }
                ),
            ),
            "does not publish the relation",
        ),
        (
            replaced(
                "contracts/products/risk/settled_positions/contract.json",
                document(
                    {
                        **PRODUCER_CONTRACT,
                        "relations": [
                            {
                                "name": "risk.settled_positions",
                                "fields": [{"required": True, "type": "string"}],
                            }
                        ],
                    }
                ),
            ),
            "unnamed field",
        ),
        (
            replaced(
                "manifests/products/risk/settled_positions.json",
                document({"product": "risk.settled_positions", "schema": "ergasterion.product-runtime/v1"}),
            ),
            "has no materialisation",
        ),
        (
            replaced(
                "contracts/products/risk/settled_positions/contract.json",
                document({**PRODUCER_CONTRACT, "identity": {"domain": "risk", "name": "settled_positions"}}),
            ),
            "no producer major",
        ),
        (
            replaced(
                "manifests/products/risk/settled_positions.json",
                document({**PRODUCER_MANIFEST, "materialisation": {"intent": "table", "unique_key": "position_id"}}),
            ),
            "invalid unique key",
        ),
    ],
)
def test_missing_or_malformed_generated_artefacts_are_refused(tmp_path, files, reason):
    runner = FakeErgasterionRunner(files=files)

    with pytest.raises(ErgasterionRouteError, match=reason):
        generated(tmp_path, runner)


def test_a_generated_artefact_that_is_not_text_is_refused(tmp_path):
    runner = FakeErgasterionRunner(
        files=without("graphs/products/product-graph.json"),
        binary={"graphs/products/product-graph.json": b"\xff\xfe not text"},
    )

    with pytest.raises(ErgasterionRouteError, match="is not text"):
        generated(tmp_path, runner)


def test_an_unmappable_published_field_type_is_refused(tmp_path):
    producer = json.loads(json.dumps(PRODUCER_CONTRACT))
    producer["relations"][0]["fields"][0]["type"] = {"name": "geography"}
    runner = FakeErgasterionRunner(
        files=replaced("contracts/products/risk/settled_positions/contract.json", document(producer))
    )

    with pytest.raises(ErgasterionRouteError, match="unmappable field type"):
        generated(tmp_path, runner)


def test_generated_artefacts_carry_a_distinct_reviewer_and_an_adjudicated_disposition(tmp_path):
    result = generated(tmp_path, FakeErgasterionRunner())
    reviewer = Identity(identifier="generation-reviewer", version="r1", digest="sha256:review-digest")

    accepted = result.adjudicated(reviewer=reviewer, disposition=GenerationDisposition.ACCEPTED)
    evidence = accepted.build_evidence()

    assert accepted.reviewer.identifier != result.generated_by
    assert len(evidence) == len(result.artefact_digests)
    assert evidence[0].evidence_id == result.artefact_digests[0][0]
    assert evidence[0].digest == result.artefact_digests[0][1]
    assert "generation-reviewer" in evidence[0].summary


@pytest.mark.parametrize(
    ("reviewer", "disposition", "reason"),
    [
        (
            Identity(identifier="generation-actor", version="r1", digest="sha256:review-digest"),
            GenerationDisposition.ACCEPTED,
            "distinct from the generating actor",
        ),
        ("generation-reviewer", GenerationDisposition.ACCEPTED, "must be a declared identity"),
        (
            Identity(identifier="generation-reviewer", version="r1", digest="sha256:review-digest"),
            "accepted",
            "adjudicated disposition",
        ),
    ],
)
def test_generated_artefacts_refuse_an_unadjudicated_reference(tmp_path, reviewer, disposition, reason):
    result = generated(tmp_path, FakeErgasterionRunner())

    with pytest.raises(ErgasterionRouteError, match=reason):
        result.adjudicated(reviewer=reviewer, disposition=disposition)


@pytest.mark.parametrize(
    "disposition", [GenerationDisposition.PENDING, GenerationDisposition.REJECTED]
)
def test_unaccepted_generation_is_never_referenced_as_build_evidence(tmp_path, disposition):
    result = generated(tmp_path, FakeErgasterionRunner())
    reviewer = Identity(identifier="generation-reviewer", version="r1", digest="sha256:review-digest")

    with pytest.raises(ErgasterionRouteError, match="after an accepted adjudication"):
        result.adjudicated(reviewer=reviewer, disposition=disposition).build_evidence()


def test_the_subprocess_runner_refuses_an_empty_command():
    with pytest.raises(ErgasterionRouteError, match="an Ergasterion command is required"):
        SubprocessErgasterionRunner(command=()).run(("--help",), working_directory=None)


def module_level_delivery_imports(path: Path) -> tuple[str, ...]:
    """Every delivery-tool module a test file imports outside a function or class."""
    found: list[str] = []

    def visit(body) -> None:
        for statement in body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(statement, ast.Import):
                found.extend(
                    alias.name
                    for alias in statement.names
                    if alias.name.partition(".")[0] in DELIVERY_TOOL_ROOTS
                )
            elif isinstance(statement, ast.ImportFrom) and not statement.level and statement.module:
                if statement.module.partition(".")[0] in DELIVERY_TOOL_ROOTS:
                    found.append(statement.module)
            for _, value in ast.iter_fields(statement):
                if isinstance(value, list) and any(isinstance(item, ast.stmt) for item in value):
                    visit([item for item in value if isinstance(item, ast.stmt)])

    visit(ast.parse(path.read_text(encoding="utf-8"), filename=path.name).body)
    return tuple(found)


def live_test_modules() -> list[Path]:
    return sorted((ROOT / "tests/product").glob("test_*_live.py"))


def test_live_test_modules_import_delivery_tools_inside_the_test_body():
    modules = live_test_modules()

    assert modules, "the product suite declares no live test module"
    assert {path.name: module_level_delivery_imports(path) for path in modules} == {
        path.name: () for path in modules
    }


def test_a_module_level_delivery_import_reddens_the_import_placement_check(tmp_path):
    source = live_test_modules()[0]
    copy = tmp_path / source.name
    copy.write_text(
        "import ergasterion\n" + source.read_text(encoding="utf-8"), encoding="utf-8"
    )

    assert module_level_delivery_imports(copy) == ("ergasterion",)
