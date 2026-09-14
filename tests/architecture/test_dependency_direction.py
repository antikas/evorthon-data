import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[2]
SOURCE_ROOT = ROOT / "src"
D2_SOURCE = ROOT / "docs/architecture/solution-architecture.d2"
COMPONENT_MARKER = re.compile(r"^\s*# evorthon-component: ([a-z][a-z0-9_]*)\s*$", re.MULTILINE)
# Intake is artefact-first and reads what is in hand with base tools. No parser
# is built for an artefact shape, so no module carries a parser's name.
PARSER_MODULE_NAMES = {"parser", "parsers"}
DELIVERY_TOOL_COMPONENTS = {
    "autobuild": "autobuild",
    "autobuild_factory": "autobuild",
    "ergasterion": "ergasterion",
    "ergasterion_factory": "ergasterion",
    "pinax": "pinax",
    "pinax_tracker": "pinax",
}


def renderer_module():
    specification = importlib.util.spec_from_file_location("evorthon_render_architecture", ROOT / "scripts/render_architecture.py")
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


RENDERER = renderer_module()
ARCHITECTURE = RENDERER.parse(D2_SOURCE)


def product_source_files():
    return sorted((SOURCE_ROOT / "evorthon_data").rglob("*.py"))


def component_for(path: Path) -> str:
    matches = COMPONENT_MARKER.findall(path.read_text(encoding="utf-8"))
    assert len(matches) == 1, f"{path.relative_to(ROOT)} must declare exactly one architecture component"
    component = matches[0]
    assert component in ARCHITECTURE.nodes, f"{path.relative_to(ROOT)} declares unknown component {component}"
    return component


def module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def component_modules() -> dict[str, str]:
    return {module_name(path): component_for(path) for path in product_source_files()}


def imported_modules(path: Path) -> set[str]:
    return imported_modules_from_source(
        path.read_text(encoding="utf-8"),
        source_module=module_name(path),
        is_package=path.name == "__init__.py",
    )


def imported_modules_from_source(source: str, *, source_module: str, is_package: bool) -> set[str]:
    package = source_module if is_package else source_module.rpartition(".")[0]
    imports: set[str] = set()
    tree = ast.parse(source, filename=source_module)
    for statement in ast.walk(tree):
        if isinstance(statement, ast.Import):
            imports.update(alias.name for alias in statement.names if is_tracked_module(alias.name))
        elif isinstance(statement, ast.ImportFrom):
            target = (
                importlib.util.resolve_name("." * statement.level + (statement.module or ""), package)
                if statement.level
                else statement.module
            )
            if target and is_tracked_module(target):
                imported_names = {f"{target}.{alias.name}" for alias in statement.names if alias.name != "*"}
                imports.update(imported_names or {target})
    return imports


def is_tracked_module(module: str) -> bool:
    return module.startswith("evorthon_data") or module.partition(".")[0] in DELIVERY_TOOL_COMPONENTS


def component_edges_for_imports(
    source_component: str,
    imports: set[str],
    modules: dict[str, str],
) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for imported in imports:
        candidate = imported
        target_component = None
        while candidate:
            target_component = modules.get(candidate) or DELIVERY_TOOL_COMPONENTS.get(candidate)
            if target_component:
                break
            candidate = candidate.rpartition(".")[0]
        assert target_component, f"{source_component} imports an unmapped tracked module {imported}"
        if target_component != source_component:
            edges.add((source_component, target_component))
    return edges


def imported_component_edges() -> set[tuple[str, str]]:
    modules = component_modules()
    edges: set[tuple[str, str]] = set()
    for path in product_source_files():
        edges.update(component_edges_for_imports(component_for(path), imported_modules(path), modules))
    return edges

def forbidden_edges(edges: set[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted(edges & ARCHITECTURE.forbidden_dependencies)


def test_architecture_owner_and_render_are_exact():
    subprocess.run([sys.executable, "scripts/render_architecture.py", "--check"], cwd=ROOT, check=True)


def test_d2_names_the_full_target_ownership_model():
    required = {
        "engagement",
        "verification_domain",
        "verification_core",
        "verification_enforcement",
        "verification_workflows",
        "verification_ports",
        "verification_adapters",
        "verification_presentation",
        "security_model_egress",
        "koine_projection",
        "composition",
    }
    assert required <= set(ARCHITECTURE.nodes)
    assert ARCHITECTURE.explicit_forbidden_dependencies <= ARCHITECTURE.forbidden_dependencies


def test_d2_is_the_named_authority_in_instruction_and_context_surfaces():
    for path in (ROOT / "AGENTS.md", ROOT / "context/tool-boundaries.md"):
        text = path.read_text(encoding="utf-8")
        assert "solution-architecture.d2" in text
        assert "sole owner" in text
        assert "mechanically generated" in text


def test_koine_material_is_a_validated_projection_not_a_second_owner():
    from evorthon_data.koine_projection import validate_koine_projections, validate_koine_runtime_adapters

    text = (ROOT / "koine/INDEX.md").read_text(encoding="utf-8").lower()
    assert "validation checks template fields" in text
    assert "architecture reference" in text
    assert "the runtime defines lifecycle, verification and model-access behavior" in text
    assert validate_koine_projections(ROOT / "koine") == {}
    assert validate_koine_runtime_adapters(ROOT / "koine", ROOT / ".github") == {}


def test_koine_template_drift_reddens_the_projection_validator(tmp_path):
    from evorthon_data.koine_projection import validate_koine_projections

    projection = tmp_path / "koine"
    shutil.copytree(ROOT / "koine", projection)
    template = projection / "templates" / "outcome-brief.md"
    template.write_text(
        template.read_text(encoding="utf-8").replace("- **Open questions:**\n", ""),
        encoding="utf-8",
    )

    assert validate_koine_projections(projection) == {
        "templates/outcome-brief.md": ["missing engagement fields: open questions"]
    }


def test_missing_koine_runtime_adapter_reddens_the_projection_validator(tmp_path):
    from evorthon_data.koine_projection import validate_koine_runtime_adapters

    repository = tmp_path / "repository"
    shutil.copytree(ROOT / "koine", repository / "koine")
    shutil.copytree(ROOT / ".github", repository / ".github")
    missing = repository / ".github/prompts/koine-discover-greenfield-capabilities.prompt.md"
    missing.unlink()

    assert validate_koine_runtime_adapters(repository / "koine", repository / ".github") == {
        ".github/prompts/koine-discover-greenfield-capabilities.prompt.md": ["adapter projection is missing"]
    }


def parser_modules(source_root: Path) -> list[str]:
    """Name every module or package called parser or parsers under a source tree."""
    return sorted(
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if (path.is_dir() and path.name in PARSER_MODULE_NAMES)
        or (path.suffix == ".py" and path.stem in PARSER_MODULE_NAMES)
    )


def test_no_parser_module_exists_under_the_product_source():
    assert parser_modules(SOURCE_ROOT) == []


def test_an_injected_parser_module_reddens_the_no_parser_assertion(tmp_path):
    mirror = tmp_path / "src"
    shutil.copytree(SOURCE_ROOT, mirror)
    (mirror / "evorthon_data" / "parser.py").write_text("", encoding="utf-8")

    assert parser_modules(mirror) == ["evorthon_data/parser.py"]


def test_every_product_module_is_assigned_to_the_d2_ownership_model():
    assert component_modules()


def test_product_imports_follow_d2_allow_rules():
    observed = imported_component_edges()
    assert observed <= ARCHITECTURE.allowed_dependencies
    assert forbidden_edges(observed) == []


@pytest.mark.parametrize(
    ("source_component", "source", "expected"),
    [
        (
            "engagement",
            "from evorthon_data.verification import core\n",
            ("engagement", "verification_core"),
        ),
        ("verification_core", "import pinax\n", ("verification_core", "pinax")),
        ("verification_core", "from autobuild import run\n", ("verification_core", "autobuild")),
        ("verification_core", "import ergasterion_factory.runtime\n", ("verification_core", "ergasterion")),
    ],
)
def test_source_import_extraction_reddens_disallowed_edges(source_component, source, expected):
    imports = imported_modules_from_source(source, source_module="evorthon_data.fixture", is_package=False)
    edges = component_edges_for_imports(source_component, imports, component_modules())

    assert forbidden_edges(edges) == [expected]


@pytest.mark.parametrize(("source", "target"), sorted(ARCHITECTURE.forbidden_dependencies))
def test_every_d2_forbidden_dependency_edge_reddens(source, target):
    assert forbidden_edges({(source, target)}) == [(source, target)]


def test_stages_module_is_a_compatibility_facade_for_the_engagement_owner():
    from evorthon_data import stages as compatibility
    from evorthon_data.engagement import stages as engagement

    assert compatibility.validate_stage is engagement.validate_stage
    assert compatibility.validate_examples is engagement.validate_examples


def test_verification_base_imports_when_delivery_tool_imports_are_blocked():
    script = """
import builtins

blocked = {
    "pinax",
    "pinax_tracker",
    "autobuild",
    "autobuild_factory",
    "ergasterion",
    "ergasterion_factory",
}
original = builtins.__import__

def guarded(name, *args, **kwargs):
    if name.partition(".")[0] in blocked:
        raise ModuleNotFoundError(name)
    return original(name, *args, **kwargs)

builtins.__import__ = guarded
import evorthon_data.verification
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SOURCE_ROOT)
    subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=environment, check=True)


def test_architecture_dependency_mutation_reddens_equivalence(tmp_path):
    source = tmp_path / "architecture.d2"
    mirror = tmp_path / "architecture.md"
    svg = tmp_path / "architecture.svg"
    source.write_text(D2_SOURCE.read_text(encoding="utf-8").replace("allow:", "forbid:", 1), encoding="utf-8")
    mirror.write_text((ROOT / "docs/architecture/solution-architecture.md").read_text(encoding="utf-8"), encoding="utf-8")
    svg.write_text((ROOT / "docs/architecture/solution-architecture.svg").read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/render_architecture.py", "--check", "--source", str(source), "--mirror", str(mirror), "--svg", str(svg)], cwd=ROOT)
    assert result.returncode != 0


def test_architecture_label_mutation_reddens_equivalence(tmp_path):
    source = tmp_path / "architecture.d2"
    mirror = tmp_path / "architecture.md"
    svg = tmp_path / "architecture.svg"
    original = D2_SOURCE.read_text(encoding="utf-8")
    source.write_text(re.sub(r'"[^"]+"', '"Changed architecture label"', original, count=1), encoding="utf-8")
    mirror.write_text((ROOT / "docs/architecture/solution-architecture.md").read_text(encoding="utf-8"), encoding="utf-8")
    svg.write_text((ROOT / "docs/architecture/solution-architecture.svg").read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run([sys.executable, "scripts/render_architecture.py", "--check", "--source", str(source), "--mirror", str(mirror), "--svg", str(svg)], cwd=ROOT)
    assert result.returncode != 0
