"""The delivery extra owns the version floors; the lock is dated build evidence."""
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version


ROOT = Path(__file__).parents[2]
# Each floor is the first published version of a delivery distribution that
# carries an interface Evorthon calls. A floor rises only when the code starts
# calling a newer interface. No delivery distribution carries an upper bound.
DELIVERY_FLOORS = {
    "pinax-tracker": "0.1.3",
    "autobuild-factory": "0.5.0",
    "ergasterion-factory": "0.6.1",
}
DELIVERY_DISTRIBUTIONS = tuple(DELIVERY_FLOORS)
TEST_DISTRIBUTIONS = ("pytest", "pytest-timeout")
CEILING_OPERATORS = ("<", "<=", "==", "~=", "!=")


def requirements_by_name(requirements):
    declared = {}
    for text in requirements:
        requirement = Requirement(text)
        declared[requirement.name] = requirement
    assert len(declared) == len(requirements)
    return declared


# evorthon-verifies: EVD-README-033
def test_delivery_extra_is_the_single_range_owner_and_base_has_no_delivery_tools():
    project_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = tomllib.loads(project_text)["project"]

    assert project["requires-python"] == ">=3.11"
    assert project.get("dependencies", []) == []
    assert "path =" not in project_text and "editable" not in project_text

    extras = project["optional-dependencies"]
    assert set(extras) == {"delivery", "test"}
    declared = requirements_by_name(extras["delivery"])
    assert set(declared) == set(DELIVERY_DISTRIBUTIONS)
    test_declared = requirements_by_name(extras["test"])
    assert set(test_declared) == set(TEST_DISTRIBUTIONS)
    for requirement in test_declared.values():
        assert {specifier.operator for specifier in requirement.specifier} == {">=", "<"}
    assert "local-data" not in project_text


def test_delivery_extra_declares_a_floor_and_no_ceiling_for_every_delivery_distribution():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = requirements_by_name(project["optional-dependencies"]["delivery"])

    for distribution, floor in DELIVERY_FLOORS.items():
        specifiers = list(declared[distribution].specifier)
        ceilings = [specifier for specifier in specifiers if specifier.operator in CEILING_OPERATORS]
        assert ceilings == [], f"{distribution} declares a ceiling: {[str(one) for one in ceilings]}"
        assert [(specifier.operator, specifier.version) for specifier in specifiers] == [(">=", floor)]


def test_delivery_lock_is_dated_evidence_that_satisfies_every_declared_floor():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    declared = requirements_by_name(project["optional-dependencies"]["delivery"])

    assert lock["requires-python"] == project["requires-python"]
    locked_packages = {package["name"]: package for package in lock["package"]}
    locked_project = locked_packages[project["name"]]
    assert locked_project.get("dependencies", []) == []
    locked_requirements = {
        requirement["name"]: SpecifierSet(requirement["specifier"])
        for requirement in locked_project["metadata"]["requires-dist"]
        if requirement["name"] in DELIVERY_DISTRIBUTIONS
    }
    assert locked_requirements == {name: requirement.specifier for name, requirement in declared.items()}

    for distribution, floor in DELIVERY_FLOORS.items():
        locked_distribution = locked_packages[distribution]
        source = locked_distribution["source"]
        assert set(source) == {"registry"}
        parsed_registry = urlparse(source["registry"])
        assert parsed_registry.scheme == "https" and parsed_registry.netloc
        locked_version = Version(locked_distribution["version"])
        assert locked_version >= Version(floor), f"{distribution} {locked_version} is below its floor {floor}"
