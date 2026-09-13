"""The environment-adapter kit: reference adapters and their conformance suite.

An adopting environment writes the adapters that reach its own material. This
package is what it writes them against: two reference adapters per port
contract, the record an adapter uses to say what it is, and the suite that
reads an adapter's answers against its claims.

The kit imports the port contracts and the one owner of the machine-route and
credential shapes, and nothing else of this product. It holds no verification
domain, no workflow, no deterministic core and no wiring, so an adapter written
against it takes on none of them either. The adopter-facing contract is in the
product documentation under the verification boundary.
"""

# evorthon-component: verification_adapters
from .conformance import (
    CANDIDATE_RUNNER_CONTRACT,
    CONFORMANCE_ABSENT_REFERENCES,
    CONFORMANCE_CANDIDATE,
    CONFORMANCE_DECLARED_OUTPUTS,
    CONFORMANCE_EVIDENCE,
    CONFORMANCE_FACTS,
    CONFORMANCE_FOREIGN_FACTS,
    CONFORMANCE_OUTPUTS,
    ConformanceFinding,
    ConformanceReason,
    ConformanceReport,
    EVIDENCE_REPOSITORY_CONTRACT,
    check_conformance,
)
from .declaration import (
    ADAPTER_CAPABILITIES,
    ASSURANCE_LEVELS,
    AdapterDeclaration,
    AdapterDeclarationPort,
    DECLARED_ASSURANCE,
    ENVIRONMENT_CERTIFIED_ASSURANCE,
    HOLDING_CAPABILITIES,
    HOLDS_MATERIAL_IN_MEMORY,
    HOLDS_MATERIAL_ON_A_FILE_SYSTEM,
    OWNER_PRESENTED_ASSURANCE,
    PRESENTS_A_CERTIFICATE,
    READS_HELD_EVIDENCE,
    REPLAYS_DECLARED_OUTPUTS,
)
from .fixtures import (
    FixtureCandidateRunner,
    FixtureEvidenceRepository,
    write_fixture_material,
)
from .material import ReplayDeclaration
from .memory import InMemoryCandidateRunner, InMemoryEvidenceRepository

__all__ = [
    "ADAPTER_CAPABILITIES",
    "ASSURANCE_LEVELS",
    "AdapterDeclaration",
    "AdapterDeclarationPort",
    "CANDIDATE_RUNNER_CONTRACT",
    "CONFORMANCE_ABSENT_REFERENCES",
    "CONFORMANCE_CANDIDATE",
    "CONFORMANCE_DECLARED_OUTPUTS",
    "CONFORMANCE_EVIDENCE",
    "CONFORMANCE_FACTS",
    "CONFORMANCE_FOREIGN_FACTS",
    "CONFORMANCE_OUTPUTS",
    "ConformanceFinding",
    "ConformanceReason",
    "ConformanceReport",
    "DECLARED_ASSURANCE",
    "EVIDENCE_REPOSITORY_CONTRACT",
    "ENVIRONMENT_CERTIFIED_ASSURANCE",
    "FixtureCandidateRunner",
    "FixtureEvidenceRepository",
    "HOLDING_CAPABILITIES",
    "HOLDS_MATERIAL_IN_MEMORY",
    "HOLDS_MATERIAL_ON_A_FILE_SYSTEM",
    "InMemoryCandidateRunner",
    "InMemoryEvidenceRepository",
    "OWNER_PRESENTED_ASSURANCE",
    "PRESENTS_A_CERTIFICATE",
    "READS_HELD_EVIDENCE",
    "REPLAYS_DECLARED_OUTPUTS",
    "ReplayDeclaration",
    "check_conformance",
    "write_fixture_material",
]
