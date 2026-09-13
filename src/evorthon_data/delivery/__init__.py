"""Optional adapters for released delivery wheels.

Nothing in the base package imports delivery tools. The Pinax adapter projects
only an approval-gated delivery contract; Pinax remains the live-state owner.
The Ergasterion route generates only from a contract that declares exact
generation; Ergasterion remains the owner of the translation and its
artefacts. The AutoBuild route composes and issues one campaign run over an
already-approved item selection; AutoBuild remains the owner of selection,
sequencing, tracker writes and delivery.
"""

# evorthon-component: delivery_adapters

from .autobuild import (
    AutoBuildDeliveryRoute,
    AutoBuildItemOutcome,
    AutoBuildRouteError,
    AutoBuildRunner,
    AutoBuildRunRecord,
    DeliveryAuthority,
    QueueSelection,
    SubprocessAutoBuildRunner,
)
from .declaration_draft import (
    AdjudicatedDeclaration,
    DeclarationDraftError,
    FixtureInput,
    LayerProfile,
    ProductDeclarationDraft,
    ProductPin,
    ProposedCalculatedField,
    ProposedDeclaration,
    SegmentDeclarationRequest,
    draft_declaration,
)
from .ergasterion import (
    AdjudicatedGeneration,
    AuxiliaryLineageRecord,
    ErgasterionGenerationRoute,
    ErgasterionRouteError,
    ErgasterionRunner,
    ExactGenerationContract,
    FieldLineageRecord,
    FixtureSeed,
    GeneratedEstate,
    GenerationDisposition,
    ProductDeclaration,
    ProductEdgeRecord,
    ProductGraphReading,
    ProductNodeRecord,
    SubprocessErgasterionRunner,
)
from .pinax import (
    ApprovedContractIdentity,
    PinaxContractProjector,
    PinaxProjectionError,
    PinaxProjectionResult,
    SubprocessPinaxRunner,
)

__all__ = [
    "AdjudicatedDeclaration",
    "AdjudicatedGeneration",
    "ApprovedContractIdentity",
    "AutoBuildDeliveryRoute",
    "AutoBuildItemOutcome",
    "AutoBuildRouteError",
    "AutoBuildRunner",
    "AutoBuildRunRecord",
    "AuxiliaryLineageRecord",
    "DeclarationDraftError",
    "DeliveryAuthority",
    "ErgasterionGenerationRoute",
    "ErgasterionRouteError",
    "ErgasterionRunner",
    "ExactGenerationContract",
    "FieldLineageRecord",
    "FixtureInput",
    "FixtureSeed",
    "GeneratedEstate",
    "GenerationDisposition",
    "LayerProfile",
    "PinaxContractProjector",
    "PinaxProjectionError",
    "PinaxProjectionResult",
    "ProductDeclaration",
    "ProductDeclarationDraft",
    "ProductEdgeRecord",
    "ProductGraphReading",
    "ProductNodeRecord",
    "ProductPin",
    "ProposedCalculatedField",
    "ProposedDeclaration",
    "QueueSelection",
    "SegmentDeclarationRequest",
    "SubprocessAutoBuildRunner",
    "SubprocessErgasterionRunner",
    "SubprocessPinaxRunner",
    "draft_declaration",
]
