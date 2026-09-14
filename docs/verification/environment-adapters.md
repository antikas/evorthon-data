# Environment adapters

To verify a data product, Evorthon Data needs stored evidence and candidate outputs from the adopting environment. Your team provides adapters that supply them through two Python interfaces. The adapter kit includes reference implementations and checks for contract conformance.

Adapters use the port contracts and adapter kit. They do not import the verification domain, comparison core or workflows.

## Required methods

An **evidence repository** implements `read_evidence(evidence_id, version)`. It returns the stored bytes, declared digest, recording time, validity period and an approved summary for the requested evidence reference. Raise `EvidenceNotHeld` for an absent reference; an empty record is not a substitute.

A **candidate runner** implements:

- `declare_candidate()`: return the candidate's identity, version and declared digest.
- `produce_outputs(facts)`: return outputs produced from the supplied frozen case facts. Raise `PortRefusal` if those facts are insufficient to produce outputs.

The frozen facts are the complete input to `produce_outputs`. This interface provides no address, credential, live-source connection or live-run observation. Routine verification compares the candidate against a frozen expectation.

Expected outputs remain with the verifier. Keeping them out of the runner's input prevents the candidate from copying the answer it is being checked against.

## Adapter declarations

Both interfaces also require `declare_adapter()`, returning an `AdapterDeclaration`:

| Field | Content |
| --- | --- |
| `adapter_id` | Adapter name. |
| `version` | Adapter version. |
| `port_contract_version` | Version of the port contract it implements. |
| `capabilities` | Supported capabilities from the declared set below. |
| `assurance` | Declared assurance level. |
| `owner_presented_inputs` | Identities of inputs presented by an owner. |
| `environment_certificates` | Identities of certificate claims held by the environment. |

The final two fields carry identities. The input material, certificates and their locations remain in the adopting environment.

### Capabilities

| Capability | Declaration | Conformance check |
| --- | --- | --- |
| `replays-declared-outputs` | The runner returns outputs declared for a case. | At least one output was returned for the conformance facts. |
| `reads-held-evidence` | The repository reads evidence it holds. | It returned the conformance material it was given. |
| `holds-material-in-memory` | Material is held in memory. | Held material was returned; the interface cannot establish its storage location. |
| `holds-material-on-a-file-system` | Material is held on a file system. | Held material was returned; the interface cannot establish its storage location. |
| `presents-a-certificate` | The environment holds a certificate claim. | The declaration names at least one certificate identity. |

An adapter may declare one storage capability. Declaring both storage locations is a contradiction. Signing and retention are outside this capability set; declarations using unknown capability names fail conformance.

### Assurance levels

| Level | Declaration | Required reference |
| --- | --- | --- |
| `declared` | The environment declares the material's identity. | No additional reference. |
| `owner-presented` | A named owner presented the input. | At least one identity in `owner_presented_inputs`. |
| `environment-certified` | The environment certifies the material. | At least one identity in `environment_certificates`. |

The suite checks whether an adapter's answers support its declaration. It reports unsupported capabilities or assurance, an unknown contract version, malformed values and prohibited content. An assurance label records the environment's claim; checking the label does not verify a certificate's authority.

## Content checks

Plain values returned through an adapter are checked for machine-location and credential patterns. A matching value fails conformance.

Machine-location patterns include drive paths, network shares and hosts, absolute paths, home-directory paths, parent-directory traversal, backslash-separated paths, addresses with a scheme and local file addresses.

Credential patterns include assigned secrets and keys, presented tokens, private-key headers, credentials embedded in addresses and tokens in authorization headers. These patterns are defined centrally and used by the record checks and public-copy scanner.

Refusal messages are checked too. Report the reason for refusal without repeating a supplied value, which could disclose the content that caused the failure.

The conformance suite does not inspect an evidence record's stored bytes for these patterns. The intake workflow computes their digest and compares it with the declared digest. The adopting team controls the evidence content.

## Environment responsibilities

The adopting environment owns locations, credentials, capture, signing, retention and certification. Adapter configuration contains connection and storage details. These details have no fields in the portable contracts and must stay out of returned values, refusal messages and reports.

Conformance checks validate a declared digest's format. The intake workflow separately verifies that the supplied bytes produce that digest.

## Running conformance checks

The following example runs the supplied adapters against the kit's conformance material:

```python
from evorthon_data.verification.adapters import (
    CONFORMANCE_CANDIDATE,
    CONFORMANCE_DECLARED_OUTPUTS,
    CONFORMANCE_EVIDENCE,
    InMemoryCandidateRunner,
    InMemoryEvidenceRepository,
    check_conformance,
)

report = check_conformance(
    candidate_runner=InMemoryCandidateRunner(
        CONFORMANCE_CANDIDATE, (CONFORMANCE_DECLARED_OUTPUTS,)
    ),
    evidence_repository=InMemoryEvidenceRepository(CONFORMANCE_EVIDENCE),
)
for finding in report.findings:
    print(finding.contract, finding.member, finding.reason.value, finding.detail)
assert report.conformant
```

To check your own adapters, initialise them with the same conformance material and pass a runner, a repository or both to `check_conformance`.

| Material | Purpose |
| --- | --- |
| `CONFORMANCE_EVIDENCE` | Records the repository must hold. |
| `CONFORMANCE_CANDIDATE` | Candidate identity the runner declares. |
| `CONFORMANCE_FACTS` and `CONFORMANCE_DECLARED_OUTPUTS` | Case facts and their declared outputs. |
| `CONFORMANCE_FOREIGN_FACTS` | A case with no declared outputs; returning declared outputs or refusing is conformant. |

### Reported failures

Each finding names the port contract, contract version, method or field, and a reason. For example:

```text
EvidenceRepositoryPort evorthon.verification.ports.v1 read_evidence.summary
machine-route-carried the value carries a drive path, and a location stays in
the environment
```

Findings omit the offending value to avoid disclosing it in the report. The supported reasons are:

`declaration-missing`, `declaration-malformed`, `contract-version-unknown`, `capability-unknown`, `capability-conflicting`, `capability-not-observed`, `assurance-unknown`, `assurance-unsupported`, `value-malformed`, `machine-route-carried`, `credential-carried`, `contract-not-honoured` and `absence-not-refused`.

## Reference implementations

The kit supplies four adapters that pass conformance checks:

- `InMemoryEvidenceRepository` and `InMemoryCandidateRunner` read values supplied to their constructors.
- `FixtureEvidenceRepository` and `FixtureCandidateRunner` read material from a directory selected when they are constructed.

All four use `declared` assurance. They provide no signing, retention or certification capability.

The fixture adapters use this directory layout:

```text
evidence/<evidence name>/<version>.content
evidence/<evidence name>/<version>.record.json
candidate.json
declared-outputs/<case name>/<case version>.json
```

Callers request material by logical identity and version. Names contain letters, digits, dots, underscores or hyphens; they cannot begin with a dot or contain two consecutive dots. Invalid names receive an absent-material refusal that omits the supplied name.

`write_fixture_material` writes values in the same layout. The root directory is adapter configuration and remains absent from port values, refusal messages and reports.

## Implementing an adapter

Implement the relevant methods, declare the capabilities and assurance you can support, and run the conformance suite. Correct reported contradictions. If a finding conflicts with the port contract, report it with the declaration and behavior needed to reproduce it.
