"""The two clean-installation phases the deep harness declares, proved without installing.

Acceptance installs the product twice: once as the wheel alone, and once as the
same wheel with the exact current delivery lock. Those two installations are
expensive and they run in one place only, at acceptance. What is proved here is
the definition they run from: that both phases exist, that each one installs
into a fresh environment and runs from a scratch working directory with the
source checkout out of its reach, that each one drives the substantive commands
its distribution is supposed to answer, that each one records where the command,
the module and the distribution came from, and that both bind to one commit and
one wheel.

Every command a phase would run is answered here by a scripted installation, so
nothing in this file builds a wheel, creates an environment, installs anything
or reaches a network. One assertion below holds that line explicitly. The one
exception is the probe program: two assertions run it under this interpreter,
over directories they planted themselves, because what it looks for and where
is a property of the program rather than of its source text.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
HARNESS = ROOT / "scripts" / "deep_acceptance.py"
LANE_RUNNER = ROOT / "scripts" / "run_tests.py"

if not HARNESS.is_file():  # pragma: no cover - the harness is private
    pytest.skip(
        "the clean-installation harness is private and no projection carries it",
        allow_module_level=True,
    )


def loaded(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    specification.loader.exec_module(module)
    return module


DEEP = loaded(HARNESS, "evorthon_deep_acceptance_definition")
LANE = loaded(LANE_RUNNER, "evorthon_lane_runner_definition")

COMMIT = "a" * 40
WHEEL_DIGEST = "b" * 64
LOCKED = {"pinax-tracker": "0.1.3", "autobuild-factory": "0.5.0", "ergasterion-factory": "0.6.1"}
CASE_FIXTURES = ROOT / DEEP.CASE_MATERIAL
COMMAND_SUFFIX = ".exe" if os.name == "nt" else ""
DELIVERY_NAMES = sorted(DEEP.DELIVERY_COMMANDS.values())


def phase(name: str):
    return next(one for one in DEEP.PHASES if one.name == name)


def plant(directory: Path, *names: str) -> Path:
    """Put one command file for each name in a directory, as an install would."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        command = directory / f"{name}{COMMAND_SUFFIX}"
        command.touch()
        if os.name != "nt":
            command.chmod(0o755)
    return directory


def discoverable(directory: Path) -> dict:
    """What the probe's restricted lookup answers about one directory.

    The probe asks one directory and no other, so this is the same call under
    the same restriction, put to directories the assertion planted itself.
    """
    return {name: shutil.which(name, path=str(directory)) for name in DELIVERY_NAMES}


def current_directory_first(root: Path) -> Path:
    """A stub of the command lookup a phase environment really performs.

    On Windows the lookup of CPython 3.11, which every phase environment is
    created with, reads the current directory before the search path it was
    handed, whatever it was handed. Later interpreters do not, and the one
    this suite runs under may be either, so the stub puts that reading back
    for one child and the probe is proved against the harder lookup.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "sitecustomize.py").write_text(
        "import os, shutil\n"
        "lookup = shutil.which\n"
        "def which(cmd, mode=os.F_OK | os.X_OK, path=None):\n"
        "    if path is not None:\n"
        "        path = os.pathsep.join((os.curdir, path))\n"
        "    return lookup(cmd, mode, path)\n"
        "shutil.which = which\n",
        encoding="ascii",
    )
    return root


def probed(searched: Path, working: Path, search_path: str, lookup: Path | None = None) -> dict:
    """Run the probe program the harness hands a phase and read its answer back.

    This is the one place here that starts a child process. It installs
    nothing, builds nothing and reaches no network: it runs the program under
    this interpreter, from a working directory the assertion planted, over
    directories the assertion planted, so the restriction the probe applies is
    read off the probe itself rather than off its source text.
    """
    environment = {**os.environ, "PATH": search_path}
    if lookup is not None:
        routes = [str(lookup), os.environ.get("PYTHONPATH", "")]
        environment["PYTHONPATH"] = os.pathsep.join(route for route in routes if route)
    child = subprocess.run(
        [sys.executable, "-c", DEEP.origin_probe_source(searched)],
        cwd=working,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )

    assert child.returncode == 0, child.stderr
    return json.loads(child.stdout)


def words_of(name: str, kind: str) -> list[tuple[str, ...]]:
    return [command.words for command in phase(name).commands if command.runner == kind]


def installed_origin(working: Path, **overrides) -> dict:
    """What one scripted installation reports about itself."""
    environment = working.parent / "environment"
    origin = {
        "module location": str(environment / "site-packages" / "evorthon_data" / "__init__.py"),
        "imported distribution": "1.0.0",
        "working directory": str(working),
        "import roots": ["", str(working)],
        "delivery commands": {name: None for name in DELIVERY_NAMES},
        DEEP.DELIVERY_COMMAND_DIRECTORY: str(environment / "Scripts"),
    }
    origin.update(overrides)
    return origin


def reported(installed: bool) -> dict:
    """What the shipped capability route reports in each distribution."""
    return {
        name: {"installed": installed, "version": LOCKED[name] if installed else None}
        for name in DEEP.DELIVERY_DISTRIBUTIONS
    }


class FakeInstallation:
    """One installation that answers every command a phase would run.

    It executes nothing. A probe is answered with the origins the caller
    scripted, the capability route with the capabilities it scripted, and every
    other command with empty output unless the caller asked for one to fail.
    """

    def __init__(self, working: Path, *, origin: dict, capabilities: dict, failing: str | None = None):
        self.working = working
        self.origin = origin
        self.capabilities = capabilities
        self.failing = failing
        self.calls: list[tuple[list[str], str]] = []

    @property
    def environment(self) -> Path:
        return self.working.parent / "environment"

    def resolve(self, name: str) -> str:
        return str(self.environment / f"{name}.exe")

    def interpreter(self) -> Path:
        return self.environment / "Scripts" / "python.exe"

    def commands(self) -> Path:
        """The executable directory of this environment, which a phase asks."""
        return self.interpreter().parent

    def run(self, command, cwd) -> str:
        self.calls.append(([str(word) for word in command], str(cwd)))
        if self.failing is not None and self.failing in command:
            raise RuntimeError(f"command failed: {self.failing}")
        if "-c" in command:
            return json.dumps(self.origin)
        if command[-1] == "diagnose":
            return json.dumps({"product": "evorthon-data", "capabilities": self.capabilities})
        return ""

    def record_for(self, name: str) -> dict:
        return DEEP.bound_phase_record(phase(name), COMMIT, WHEEL_DIGEST)

    def drive(self, name: str, **overrides) -> dict:
        record = overrides.pop("record", None) or self.record_for(name)
        return DEEP.run_phase(
            phase(name),
            record,
            runner=self.run,
            resolve=self.resolve,
            python=self.interpreter(),
            working_directory=self.working,
            locked=overrides.pop("locked", LOCKED),
            **overrides,
        )


@pytest.fixture
def base_installation(tmp_path: Path) -> FakeInstallation:
    """The wheel alone: an environment whose executable directory holds no tool."""
    working = tmp_path / "base-working-directory"
    working.mkdir()
    installation = FakeInstallation(
        working, origin=installed_origin(working), capabilities=reported(False)
    )
    installation.origin["delivery commands"] = discoverable(plant(installation.commands()))
    return installation


@pytest.fixture
def full_installation(tmp_path: Path) -> FakeInstallation:
    """The wheel and the delivery lock: every locked tool inside the environment."""
    working = tmp_path / "full-working-directory"
    working.mkdir()
    installation = FakeInstallation(
        working, origin=installed_origin(working), capabilities=reported(True)
    )
    installation.origin["delivery commands"] = discoverable(
        plant(installation.commands(), *DELIVERY_NAMES)
    )
    return installation


# --- the two phase definitions -------------------------------------------------


def test_the_harness_declares_one_phase_for_each_distribution_and_no_other():
    assert [one.name for one in DEEP.PHASES] == [DEEP.BASE_PHASE, DEEP.FULL_PHASE]
    assert phase(DEEP.BASE_PHASE).installed == (DEEP.WHEEL,)
    assert phase(DEEP.FULL_PHASE).installed == (
        DEEP.LOCKED_DELIVERY,
        DEEP.LOCKED_ASSERTIONS,
        DEEP.WHEEL,
    )


def test_every_phase_installs_into_a_fresh_environment_and_runs_from_a_scratch_directory():
    for one in DEEP.PHASES:
        assert one.environment == DEEP.FRESH_ENVIRONMENT
        assert one.working_directory == DEEP.SCRATCH_WORKING_DIRECTORY
        assert one.isolation == DEEP.SOURCE_ABSENT


def test_every_phase_records_the_origins_a_reader_reads_the_answer_by():
    for one in DEEP.PHASES:
        assert one.records == DEEP.RECORDED_ORIGINS
    assert set(DEEP.RECORDED_ORIGINS) == {
        "entry point",
        "imported distribution",
        "module location",
        "source commit",
        "wheel sha256",
    }


def test_the_base_phase_drives_one_committed_case_through_the_installed_entry_point():
    driven = words_of(DEEP.BASE_PHASE, DEEP.INSTALLED_ENTRY_POINT)
    routes = [words[1] for words in driven if words[0] == "verification"]

    assert routes == list(DEEP.VERIFICATION_ROUTES)
    assert words_of(DEEP.BASE_PHASE, DEEP.ENVIRONMENT_INTERPRETER) == []
    assert phase(DEEP.BASE_PHASE).material == DEEP.CASE_MATERIAL
    for words in driven:
        if words[0] != "verification":
            continue
        assert words[2:6] == ("--repository", ".", "--records-root", DEEP.RECORDS_ROOT)
        assert DEEP.CASE_DOCUMENT in words
        assert DEEP.EVIDENCE_ADAPTER in words and DEEP.CANDIDATE_ADAPTER in words
    assert DEEP.MATERIAL_DOCUMENT in driven[-1]


def test_the_full_phase_runs_both_shared_engagement_lifecycles_through_the_installed_package():
    driven = words_of(DEEP.FULL_PHASE, DEEP.ENVIRONMENT_INTERPRETER)

    assert len(driven) == 1
    assert driven[0][:2] == ("-m", "pytest")
    assert driven[0][-2:] == DEEP.LIFECYCLE_MODULES
    assert phase(DEEP.FULL_PHASE).material == DEEP.CANDIDATE_MATERIAL


def test_the_base_phase_forbids_every_delivery_tool_and_the_full_phase_requires_them():
    assert phase(DEEP.BASE_PHASE).absent == DEEP.DELIVERY_DISTRIBUTIONS
    assert phase(DEEP.BASE_PHASE).present == ()
    assert phase(DEEP.FULL_PHASE).present == DEEP.DELIVERY_DISTRIBUTIONS
    assert phase(DEEP.FULL_PHASE).absent == ()


# --- the gate over the definition ----------------------------------------------


def test_the_definition_gate_is_green_on_the_table_the_harness_ships():
    assert DEEP.harness_definition_findings() == []


def without(name: str):
    return tuple(one for one in DEEP.PHASES if one.name != name)


def changed(name: str, **fields):
    import dataclasses

    return tuple(
        dataclasses.replace(one, **fields) if one.name == name else one for one in DEEP.PHASES
    )


def test_omitting_the_verification_phase_reddens_the_definition_gate():
    assert "no phase drives one committed verification case" in DEEP.harness_definition_findings(
        without(DEEP.BASE_PHASE)
    )


def test_omitting_the_lifecycle_phase_reddens_the_definition_gate():
    assert "no phase runs both shared engagement lifecycles" in DEEP.harness_definition_findings(
        without(DEEP.FULL_PHASE)
    )


@pytest.mark.parametrize("name", [DEEP.BASE_PHASE, DEEP.FULL_PHASE])
def test_omitting_a_source_isolation_rule_reddens_the_definition_gate(name):
    findings = DEEP.harness_definition_findings(changed(name, isolation=""))

    assert findings == [f"a phase declares no source isolation rule: {name}"]


@pytest.mark.parametrize("origin", DEEP.RECORDED_ORIGINS)
def test_omitting_one_recorded_origin_reddens_the_definition_gate(origin):
    kept = tuple(one for one in DEEP.RECORDED_ORIGINS if one != origin)

    findings = DEEP.harness_definition_findings(changed(DEEP.FULL_PHASE, records=kept))

    assert findings == [f"a phase records no {origin} origin: {DEEP.FULL_PHASE}"]


def test_omitting_one_lifecycle_module_reddens_the_definition_gate():
    kept = phase(DEEP.FULL_PHASE).commands[:1]

    findings = DEEP.harness_definition_findings(changed(DEEP.FULL_PHASE, commands=kept))

    assert findings == [f"the full phase runs no lifecycle: {module}" for module in DEEP.LIFECYCLE_MODULES]


def test_omitting_one_verification_route_reddens_the_definition_gate():
    kept = phase(DEEP.BASE_PHASE).commands[:2]

    findings = DEEP.harness_definition_findings(changed(DEEP.BASE_PHASE, commands=kept))

    assert findings == ["the base phase drives no verify route"]


def test_a_base_phase_that_installs_a_delivery_tool_reddens_the_definition_gate():
    findings = DEEP.harness_definition_findings(
        changed(DEEP.BASE_PHASE, installed=(DEEP.WHEEL, DEEP.LOCKED_DELIVERY))
    )

    assert findings == ["the base phase installs more than the wheel"]


# --- what each phase installs, and from which lock -----------------------------


def test_each_lock_is_exported_from_its_own_declared_extra(tmp_path: Path):
    delivery = DEEP.locked_delivery_export_command("uv", tmp_path / "delivery.txt")
    assertions = DEEP.locked_assertion_export_command("uv", tmp_path / "assertions.txt")

    assert delivery[:5] == ["uv", "export", "--locked", "--no-emit-project", "--no-dev"]
    assert delivery[5:7] == ["--extra", DEEP.DELIVERY_EXTRA]
    assert assertions[5:7] == ["--extra", DEEP.ASSERTION_EXTRA]
    for command in (delivery, assertions):
        assert command[-4:-2] == ["--format", "requirements-txt"]


def test_the_base_environment_installs_the_wheel_and_nothing_else(tmp_path: Path):
    python = tmp_path / "environment" / "python.exe"
    wheel = tmp_path / "evorthon_data-1.0.0-py3-none-any.whl"

    commands = DEEP.environment_commands(
        "uv", python, tmp_path / "environment", phase(DEEP.BASE_PHASE), wheel, {}
    )

    assert len(commands) == 2
    assert commands[0][:2] == ["uv", "venv"]
    assert commands[1][-2:] == ["--no-deps", str(wheel)]
    assert not any("--require-hashes" in command for command in commands)


def test_the_full_environment_installs_both_hash_pinned_locks_and_the_same_wheel(tmp_path: Path):
    python = tmp_path / "environment" / "python.exe"
    wheel = tmp_path / "evorthon_data-1.0.0-py3-none-any.whl"
    locks = {
        DEEP.LOCKED_DELIVERY: tmp_path / "delivery.txt",
        DEEP.LOCKED_ASSERTIONS: tmp_path / "assertions.txt",
    }

    commands = DEEP.environment_commands(
        "uv", python, tmp_path / "environment", phase(DEEP.FULL_PHASE), wheel, locks
    )

    assert len(commands) == 4
    assert [command[-1] for command in commands[1:]] == [
        str(locks[DEEP.LOCKED_DELIVERY]),
        str(locks[DEEP.LOCKED_ASSERTIONS]),
        str(wheel),
    ]
    assert all("--require-hashes" in command for command in commands[1:3])
    assert commands[3][-2] == "--no-deps"


def test_the_locked_delivery_versions_are_read_from_the_export_the_phase_installs():
    # The character a continued line of an export ends with, written by code
    # point so this file spells out no machine route of its own.
    continuation = chr(92)
    exported = (
        "# generated by the exporter\n"
        f"pinax-tracker==0.1.3 {continuation}\n"
        "    --hash=sha256:" + "0" * 64 + "\n"
        f"autobuild_factory==0.5.0 ; python_full_version >= '3.11' {continuation}\n"
        "    --hash=sha256:" + "1" * 64 + "\n"
        "ergasterion-factory==0.6.1\n"
        "packaging==24.0\n"
    )

    assert DEEP.locked_versions(exported) == LOCKED


# --- the child environment one phase runs in -----------------------------------


def test_a_phase_child_carries_no_inherited_import_route(tmp_path: Path, monkeypatch):
    python = tmp_path / "environment" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    uv = tmp_path / "tools" / "uv.exe"
    uv.parent.mkdir()
    uv.touch()
    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    monkeypatch.setenv("PYTHONSTARTUP", str(ROOT / "startup.py"))

    child = DEEP.phase_command_environment(python)

    assert "PYTHONPATH" not in child and "PYTHONSTARTUP" not in child
    assert child["PYTHONNOUSERSITE"] == "1"
    assert child["PATH"].startswith(str(python.parent.resolve()))
    assert DEEP.fresh_command_environment(python, str(uv))["PYTHONPATH"] == str(ROOT / "src")


def test_a_phase_child_looks_commands_up_inside_the_fresh_environment_only(tmp_path: Path):
    """The directory of the resolved uv executable is the harness's route alone.

    On a workstation that directory also holds the delivery tools the user
    installed globally, so a phase child that carried it would answer about
    the workstation. The harness's own checks still need uv and keep it.
    """
    python = tmp_path / "environment" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    uv = plant(tmp_path / "user-tools", "uv", *DELIVERY_NAMES) / f"uv{COMMAND_SUFFIX}"

    child = DEEP.phase_command_environment(python)
    harness = DEEP.harness_command_environment(python, str(uv))

    assert child["PATH"].split(os.pathsep) == [
        str(python.parent.resolve()),
        str(python.parent.parent.resolve()),
    ]
    assert str(uv.parent.resolve()) not in child["PATH"].split(os.pathsep)
    assert str(uv.parent.resolve()) in harness["PATH"].split(os.pathsep)
    assert "PYTHONPATH" not in harness and harness["PYTHONNOUSERSITE"] == "1"


def test_the_phase_children_and_the_harness_children_take_the_environment_each_is_owed():
    source = HARNESS.read_text(encoding="utf-8")

    assert "child = phase_command_environment(python)" in source
    assert "candidate_environment = harness_command_environment(" in source


def test_the_origin_probe_asks_the_environment_executable_directory_and_records_it(tmp_path: Path):
    directory = tmp_path / "environment" / "Scripts"

    source = DEEP.origin_probe_source(directory)

    assert "searched = " + repr(str(directory)) in source
    assert "shutil.which(name, path=searched)" in source
    assert "shutil.which(name)" not in source
    assert "os.path.realpath(os.path.dirname(found)) == os.path.realpath(searched)" in source
    assert repr(DEEP.DELIVERY_COMMAND_DIRECTORY) + ": searched" in source
    assert "import evorthon_data" in source


def test_the_probe_takes_a_hit_from_the_executable_directory_and_no_hit_beside_it(tmp_path: Path):
    """An explicit search path is not the whole restriction.

    The lookup reads the current directory first on Windows whatever path it
    was given, and a phase runs from a working directory that holds material.
    A hit is the environment's answer only when it came out of the directory
    that was searched.
    """
    directory = plant(tmp_path / "environment" / "Scripts")
    working = plant(tmp_path / "working-directory", "autobuild")
    workstation = plant(tmp_path / "user-tools", *DELIVERY_NAMES)
    lookup = current_directory_first(tmp_path / "lookup-stub")

    ignored = probed(directory, working, str(workstation), lookup)
    plant(directory, "pinax")
    kept = probed(directory, working, str(workstation), lookup)

    assert ignored["delivery commands"] == {name: None for name in DELIVERY_NAMES}
    assert ignored[DEEP.DELIVERY_COMMAND_DIRECTORY] == str(directory)
    assert kept["delivery commands"]["autobuild"] is None
    assert kept["delivery commands"]["ergasterion"] is None
    assert Path(kept["delivery commands"]["pinax"]).parent == directory


def test_the_probe_program_itself_leaves_the_base_phase_green_beside_a_stocked_workstation(
    base_installation, tmp_path: Path
):
    """The rule and the program that feeds it, proved together against one child."""
    workstation = plant(tmp_path / "user-tools", *DELIVERY_NAMES)
    answered = probed(base_installation.commands(), base_installation.working, str(workstation))
    base_installation.origin["delivery commands"] = answered["delivery commands"]
    base_installation.origin[DEEP.DELIVERY_COMMAND_DIRECTORY] = answered[
        DEEP.DELIVERY_COMMAND_DIRECTORY
    ]

    record = base_installation.drive(DEEP.BASE_PHASE)

    assert answered[DEEP.DELIVERY_COMMAND_DIRECTORY] == str(base_installation.commands())
    assert record["status"] == "green"
    assert record["delivery commands"] == {name: None for name in DELIVERY_NAMES}
    assert shutil.which("pinax", path=str(workstation)) is not None


# --- one phase run, answered by a scripted installation ------------------------


def test_the_base_phase_records_its_origins_and_drives_every_declared_command(base_installation):
    record = base_installation.drive(DEEP.BASE_PHASE)

    assert record["status"] == "green"
    assert record["origin"] == {
        "entry point": base_installation.resolve(DEEP.PRODUCT_COMMAND),
        "imported distribution": "1.0.0",
        "module location": base_installation.origin["module location"],
        "source commit": COMMIT,
        "wheel sha256": WHEEL_DIGEST,
    }
    assert record["import roots"] == base_installation.origin["import roots"]
    assert [entry["names"] for entry in record["commands"]] == [
        command.names for command in phase(DEEP.BASE_PHASE).commands
    ]
    probe, *driven = base_installation.calls
    assert probe[0][1] == "-c" and "import evorthon_data" in probe[0][2]
    assert all(call[1] == str(base_installation.working) for call in base_installation.calls)
    assert [call[0][0] for call in driven] == [
        base_installation.resolve(DEEP.PRODUCT_COMMAND)
    ] * len(driven)
    assert "intake-case" in driven[1][0] and "verify" in driven[2][0]


def test_the_full_phase_runs_the_lifecycles_through_its_own_interpreter(full_installation):
    record = full_installation.drive(DEEP.FULL_PHASE)

    assert record["status"] == "green"
    lifecycle = next(
        call for call in full_installation.calls if "pytest" in call[0]
    )
    assert lifecycle[0][0] == str(full_installation.interpreter())
    assert lifecycle[0][-2:] == list(DEEP.LIFECYCLE_MODULES)
    assert lifecycle[1] == str(full_installation.working)
    assert record["capabilities"] == reported(True)
    helped = [call[0] for call in full_installation.calls if call[0][-1] == "--help"]
    assert [Path(call[0]).stem for call in helped] == [
        DEEP.DELIVERY_COMMANDS[name] for name in DEEP.DELIVERY_DISTRIBUTIONS
    ]


def test_a_delivery_distribution_installed_beside_the_base_wheel_is_refused(base_installation):
    base_installation.capabilities = reported(True)

    with pytest.raises(RuntimeError, match="a delivery capability this phase forbids is installed"):
        base_installation.drive(DEEP.BASE_PHASE)


def test_a_delivery_command_discoverable_in_the_base_phase_is_refused(base_installation):
    base_installation.origin["delivery commands"]["pinax"] = str(
        base_installation.environment / "pinax.exe"
    )

    with pytest.raises(RuntimeError, match="a delivery command this phase forbids is discoverable"):
        base_installation.drive(DEEP.BASE_PHASE)


def test_a_delivery_command_on_the_harness_search_path_leaves_the_base_phase_green(
    base_installation, tmp_path: Path, monkeypatch
):
    """A workstation holding the tools elsewhere says nothing about the wheel."""
    workstation = plant(tmp_path / "user-tools", *DELIVERY_NAMES)
    monkeypatch.setenv("PATH", str(workstation))

    record = base_installation.drive(DEEP.BASE_PHASE)

    found = shutil.which("pinax")
    assert found is not None and Path(found).parent == workstation
    assert record["status"] == "green"
    assert record["delivery commands"] == {name: None for name in DELIVERY_NAMES}
    assert record[DEEP.DELIVERY_COMMAND_DIRECTORY] == str(base_installation.commands())


def test_a_delivery_command_inside_the_fresh_environment_reddens_the_base_phase(base_installation):
    base_installation.origin["delivery commands"] = discoverable(
        plant(base_installation.commands(), "pinax")
    )

    with pytest.raises(
        RuntimeError, match="a delivery command this phase forbids is discoverable: pinax-tracker"
    ):
        base_installation.drive(DEEP.BASE_PHASE)


def test_a_phase_that_searched_another_directory_than_its_own_is_refused(
    base_installation, tmp_path: Path
):
    base_installation.origin[DEEP.DELIVERY_COMMAND_DIRECTORY] = str(plant(tmp_path / "user-tools"))

    with pytest.raises(RuntimeError, match="searched for outside the phase environment"):
        base_installation.drive(DEEP.BASE_PHASE)


def test_the_full_phase_holds_every_locked_command_inside_its_own_environment(full_installation):
    record = full_installation.drive(DEEP.FULL_PHASE)

    assert record["status"] == "green"
    assert sorted(record["delivery commands"]) == DELIVERY_NAMES
    assert all(
        Path(found).parent == full_installation.commands()
        for found in record["delivery commands"].values()
    )
    assert record["capabilities"] == reported(True)
    assert record[DEEP.DELIVERY_COMMAND_DIRECTORY] == str(full_installation.commands())


def test_a_locked_command_missing_from_the_fresh_environment_reddens_the_full_phase(
    full_installation, tmp_path: Path, monkeypatch
):
    """The workstation holding the same tool elsewhere does not answer for it."""
    workstation = plant(tmp_path / "user-tools", *DELIVERY_NAMES)
    monkeypatch.setenv("PATH", str(workstation))
    (full_installation.commands() / f"pinax{COMMAND_SUFFIX}").unlink()
    full_installation.origin["delivery commands"] = discoverable(full_installation.commands())

    with pytest.raises(
        RuntimeError, match="a locked delivery command is not in the fresh environment: pinax-tracker"
    ):
        full_installation.drive(DEEP.FULL_PHASE)


def test_a_full_phase_missing_a_locked_capability_is_refused(full_installation):
    full_installation.capabilities["pinax-tracker"] = {"installed": False, "version": None}

    with pytest.raises(RuntimeError, match="a locked delivery capability is not installed"):
        full_installation.drive(DEEP.FULL_PHASE)


def test_a_full_phase_holding_another_version_than_the_lock_is_refused(full_installation):
    full_installation.capabilities["ergasterion-factory"] = {"installed": True, "version": "9.9.9"}

    with pytest.raises(RuntimeError, match="is not the locked version"):
        full_installation.drive(DEEP.FULL_PHASE)


def test_a_phase_importing_the_source_checkout_is_refused(base_installation):
    base_installation.origin["import roots"] = ["", str(ROOT / "src")]

    with pytest.raises(RuntimeError, match="an import route resolves inside the source checkout"):
        base_installation.drive(DEEP.BASE_PHASE)


def test_a_phase_whose_module_comes_from_the_source_checkout_is_refused(base_installation):
    base_installation.origin["module location"] = str(ROOT / "src/evorthon_data/__init__.py")

    with pytest.raises(RuntimeError, match="the imported module resolves inside the source checkout"):
        base_installation.drive(DEEP.BASE_PHASE)


def test_a_phase_whose_module_comes_from_beside_its_material_is_refused(base_installation):
    """A module resolved out of the working directory is material, not an installation."""
    base_installation.origin["module location"] = str(
        base_installation.working / "src" / "evorthon_data" / "__init__.py"
    )

    with pytest.raises(RuntimeError, match="resolves outside the phase environment"):
        base_installation.drive(DEEP.BASE_PHASE)


def test_a_phase_running_inside_the_source_checkout_is_refused(base_installation):
    base_installation.origin["working directory"] = str(ROOT / "tests")

    with pytest.raises(RuntimeError, match="the working directory sits inside the source checkout"):
        base_installation.drive(DEEP.BASE_PHASE)


def test_the_isolation_rule_reads_every_route_against_the_checkout_it_names(tmp_path: Path):
    origin = installed_origin(tmp_path)

    assert DEEP.source_leaks(origin, ROOT) == []
    assert DEEP.source_leaks(origin, tmp_path.parent) == [
        "the working directory sits inside the source checkout",
        "an import route resolves inside the source checkout: ",
        "an import route resolves inside the source checkout: " + str(tmp_path),
        "the imported module resolves inside the source checkout",
    ]


# --- a failing phase, and the binding a reader holds it to ---------------------


def test_a_failing_installed_command_keeps_its_binding_and_carries_its_own_detail(base_installation):
    base_installation.failing = "verify"
    record = base_installation.record_for(DEEP.BASE_PHASE)

    with pytest.raises(RuntimeError, match="command failed: verify"):
        base_installation.drive(DEEP.BASE_PHASE, record=record)

    assert record["status"] == "red"
    assert record["origin"]["source commit"] == COMMIT
    assert record["origin"]["wheel sha256"] == WHEEL_DIGEST
    assert [entry["names"] for entry in record["commands"]] == [
        phase(DEEP.BASE_PHASE).commands[0].names,
        phase(DEEP.BASE_PHASE).commands[1].names,
    ]


@pytest.mark.parametrize(
    ("field", "wrong", "reported_as"),
    [("source commit", "c" * 40, "another commit"), ("wheel sha256", "d" * 64, "another wheel")],
)
def test_a_phase_record_naming_another_commit_or_wheel_is_refused(field, wrong, reported_as):
    record = DEEP.bound_phase_record(phase(DEEP.BASE_PHASE), COMMIT, WHEEL_DIGEST)
    record["origin"][field] = wrong

    with pytest.raises(RuntimeError, match=f"names {reported_as}"):
        DEEP.refuse_unbound_phase(record, COMMIT, WHEEL_DIGEST)

    DEEP.refuse_unbound_phase(
        DEEP.bound_phase_record(phase(DEEP.BASE_PHASE), COMMIT, WHEEL_DIGEST), COMMIT, WHEEL_DIGEST
    )


def deep_result(tmp_path: Path, run_id: str, **overrides) -> Path:
    result = {
        "schema": "evorthon.deep-acceptance.v4",
        "commit": COMMIT,
        "run_id": run_id,
        "terminal": True,
        "status": "green",
        "wheel": {"filename": "evorthon_data-1.0.0-py3-none-any.whl", "sha256": WHEEL_DIGEST},
        "phases": [
            DEEP.bound_phase_record(one, COMMIT, WHEEL_DIGEST) for one in DEEP.PHASES
        ],
        "not_exercised": DEEP.phase_confessions(),
    }
    result.update(overrides)
    path = tmp_path / "deep.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    return path


def test_the_lane_reader_takes_a_result_whose_phases_bind_to_the_accepted_commit(tmp_path: Path):
    path = deep_result(tmp_path, "one-run")

    result = LANE.read_deep_result(path, "one-run", COMMIT, 0)

    assert [one["phase"] for one in result["phases"]] == [DEEP.BASE_PHASE, DEEP.FULL_PHASE]


@pytest.mark.parametrize(
    ("field", "wrong", "reported_as"),
    [("source commit", "c" * 40, "another commit"), ("wheel sha256", "d" * 64, "another wheel")],
)
def test_the_lane_reader_refuses_a_phase_that_names_another_commit_or_wheel(
    tmp_path: Path, field, wrong, reported_as
):
    phases = [DEEP.bound_phase_record(one, COMMIT, WHEEL_DIGEST) for one in DEEP.PHASES]
    phases[1]["origin"][field] = wrong
    path = deep_result(tmp_path, "one-run", phases=phases)

    with pytest.raises(ValueError, match=f"names {reported_as}"):
        LANE.read_deep_result(path, "one-run", COMMIT, 0)


def test_the_lane_reader_carries_a_phase_failure_and_its_detail_into_the_verdict(tmp_path: Path):
    failed = DEEP.bound_phase_record(phase(DEEP.BASE_PHASE), COMMIT, WHEEL_DIGEST)
    failed["error"] = "command failed: verify"
    path = deep_result(
        tmp_path,
        "one-run",
        status="red",
        error="installation phase failed: base: command failed: verify",
        phases=[failed],
    )

    result = LANE.read_deep_result(path, "one-run", COMMIT, 0)

    assert result["status"] == "red"
    assert result["phases"][0]["error"] == "command failed: verify"
    assert "base" in result["error"]


def test_a_green_result_that_ran_no_phase_is_refused(tmp_path: Path):
    path = deep_result(tmp_path, "one-run", phases=[])

    with pytest.raises(ValueError, match="at least one installation phase"):
        LANE.read_deep_result(path, "one-run", COMMIT, 0)


# --- the coverage confession ---------------------------------------------------


def test_each_phase_confesses_what_it_did_not_cover():
    confessions = DEEP.phase_confessions()

    assert {one["scope"] for one in confessions} == {"base install phase", "full install phase"}
    assert all(one["reason"] for one in confessions)
    assert len(confessions) == sum(len(one.not_exercised) for one in DEEP.PHASES)


def test_the_lane_confession_carries_every_phase_confession_beside_its_own():
    confession = LANE.coverage_confession("deep", "", None, DEEP.phase_confessions())

    assert {one["scope"] for one in confession} == {
        "environment lane",
        "base install phase",
        "full install phase",
    }
    assert LANE.coverage_confession("deep", "") == [
        {"scope": "environment lane", "reason": "no environment lane is defined"}
    ]


def test_the_lane_reads_the_phase_confessions_off_the_result_it_was_given():
    detail = {"deep_acceptance": {"not_exercised": DEEP.phase_confessions()}}

    assert LANE.deep_phase_confessions(detail) == DEEP.phase_confessions()
    assert LANE.deep_phase_confessions({}) == []
    assert LANE.deep_phase_confessions({"deep_acceptance": {"rejected": "unreadable"}}) == []


# --- no assertion here installs anything ---------------------------------------


def test_no_fast_assertion_reaches_a_real_build_install_or_lookup(tmp_path: Path, monkeypatch):
    """Every phase function a fast assertion drives is answered without a child process."""

    def refuse(*args, **kwargs):
        raise AssertionError("the fast lane ran an executable call")

    monkeypatch.setattr(DEEP.subprocess, "run", refuse)
    monkeypatch.setattr(DEEP.shutil, "which", refuse)
    monkeypatch.setattr(DEEP, "call", refuse)
    working = tmp_path / "working"
    working.mkdir()
    installation = FakeInstallation(
        working, origin=installed_origin(working), capabilities=reported(False)
    )

    assert DEEP.harness_definition_findings() == []
    assert DEEP.phase_confessions()
    assert DEEP.locked_delivery_export_command("uv", tmp_path / "delivery.txt")
    assert DEEP.environment_commands(
        "uv", tmp_path / "python.exe", tmp_path, phase(DEEP.BASE_PHASE), tmp_path / "one.whl", {}
    )
    record = DEEP.run_phase(
        phase(DEEP.BASE_PHASE),
        DEEP.bound_phase_record(phase(DEEP.BASE_PHASE), COMMIT, WHEEL_DIGEST),
        runner=installation.run,
        resolve=installation.resolve,
        python=installation.interpreter(),
        working_directory=working,
        locked=LOCKED,
    )

    assert record["status"] == "green"
    assert installation.calls


def test_the_harness_runs_its_installations_from_one_place_only():
    """Only the entry point assembles a real run; every other caller is given a runner."""
    source = HARNESS.read_text(encoding="utf-8")
    body = source.split("def main() -> int:")

    assert len(body) == 2
    assert "subprocess.run" in body[0].split("def call(")[1]
    assert body[0].split("def call(")[0].count("subprocess.") == 0


def test_the_public_candidate_and_reproducible_package_checks_are_preserved():
    source = HARNESS.read_text(encoding="utf-8")

    assert "release/export_public.py" in source
    assert source.count('"scripts/check_public_candidate.py"') == 2
    for word in ("--allow-provisional", "--scan-only", "--finalize", "PUBLIC-INVENTORY.json"):
        assert word in source


# --- the committed material the base phase is driven through --------------------


def test_the_committed_case_holds_exactly_the_documents_the_base_phase_names():
    held = sorted(path.relative_to(CASE_FIXTURES).as_posix() for path in CASE_FIXTURES.rglob("*") if path.is_file())

    assert DEEP.CASE_DOCUMENT in held
    assert DEEP.MATERIAL_DOCUMENT in held
    assert f"{DEEP.ENGAGEMENT}/adapters.json" in held
    configuration = json.loads(
        (CASE_FIXTURES / DEEP.ENGAGEMENT / "adapters.json").read_text(encoding="ascii")
    )
    named = configuration["adapters"]
    assert set(named) == {DEEP.EVIDENCE_ADAPTER, DEEP.CANDIDATE_ADAPTER}
    for declared in named.values():
        assert declared["family"] == "fixture"
        assert (CASE_FIXTURES / declared["directory"]).is_dir()


def test_the_committed_case_is_one_the_shipped_command_takes_in_and_verifies(tmp_path, capsys):
    from evorthon_data import cli

    shutil.copytree(CASE_FIXTURES, tmp_path / DEEP.RECORDS_ROOT)
    words = [
        word if word != "." else str(tmp_path)
        for word in DEEP.verification_words("intake-case")
    ]

    assert cli.main(words) == 0
    taken = json.loads(capsys.readouterr().out)
    verified_words = [
        word if word != "." else str(tmp_path)
        for word in DEEP.verification_words("verify", "--material", DEEP.MATERIAL_DOCUMENT)
    ]
    assert cli.main(verified_words) == 0
    outcome = json.loads(capsys.readouterr().out)

    assert taken["status"] == "ok"
    assert taken["result"]["case"] == outcome["result"]["case"]
    assert outcome["status"] == "ok"
    assert outcome["result"]["failed clauses"] == []
    assert outcome["result"]["evidence provenance"] == "synthetic"
