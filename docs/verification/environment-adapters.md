# Environment adapters

This product never reaches into your environment. Everything it needs from you
arrives through two small read contracts, and you write the code that answers
them. This page is the contract for writing that code: what an adapter
implements, what it may claim about itself, what must never cross, what stays
on your side, and how to check an adapter before you trust it.

Nothing here needs the verification domain, the deterministic core or any
workflow. An adapter imports the port contracts and the adapter kit, and
nothing else.

## The two contracts an adapter answers

An **evidence repository** reads evidence records your environment already
holds. One method:

- `read_evidence(evidence_id, version)` returns the stored record for one
  declared reference: the stored bytes, the digest your environment declares
  about those bytes, when the record was recorded, how long it holds, and a
  short approved summary. A reference you do not hold is refused by raising
  `EvidenceNotHeld`. It is never answered with an empty record, because a
  caller must never be able to read absence as a valid empty answer.

A **candidate runner** produces candidate outputs from frozen case facts. Two
methods:

- `declare_candidate()` returns the exact candidate artefact this runner
  produces outputs from: an identity, a version and a declared digest.
- `produce_outputs(facts)` returns the outputs the candidate produces from the
  frozen facts it is given. Those facts are the whole input. There is no
  address in this contract, no credential, no route to a running source system
  and no observation of a live run, because a routine verification compares an
  approved frozen expectation against a candidate and never reaches for the
  system being replaced. If you cannot produce outputs from the facts alone,
  raise `PortRefusal` rather than reaching for anything else.

You never receive an expected output. An expected output is the oracle a result
is measured against, so handing it to a candidate would let the candidate
answer with the answer.

## The declaration every adapter adds

Both contracts take one more method, `declare_adapter()`, which returns an
`AdapterDeclaration`:

| Field | What it says |
| --- | --- |
| `adapter_id` | What this adapter is called. |
| `version` | Which version of it this is. |
| `port_contract_version` | The port contract it implements. It is the one the ports declare, and nothing else is read. |
| `capabilities` | What it can do, from the closed set below. |
| `assurance` | What its answers are worth, as one of the three levels below. |
| `owner_presented_inputs` | Identities of owner-presented input it can name. |
| `environment_certificates` | Identities of certificate claims it can name. |

The last two carry identities only. The input itself, the certificate itself
and wherever either is kept stay with you.

### The capabilities you may claim

| Capability | What it claims | How the suite sees it |
| --- | --- | --- |
| `replays-declared-outputs` | The runner answers with outputs declared for a case. | It produced at least one output for the conformance facts. |
| `reads-held-evidence` | The repository answers from evidence it holds. | It answered for the conformance material it was built over. |
| `holds-material-in-memory` | It keeps what it answers from in memory. | It answered from held material at all. |
| `holds-material-on-a-file-system` | It keeps what it answers from on a file system. | It answered from held material at all. |
| `presents-a-certificate` | It can name a certificate claim your environment holds. | Its declaration names at least one. |

Two things follow from that table. A port shows that material is held, never
which side of the machine holds it, so an adapter names one place; claiming
both is a contradiction and is refused. And signing and retention have no name
in this set at all, because neither crosses a read surface. An adapter that
invents a name for one is refused as claiming a capability this product does
not name.

### The assurance you may declare

| Level | What it claims | What it needs |
| --- | --- | --- |
| `declared` | The material is what your environment says it is. | Nothing further. |
| `owner-presented` | A named owner presented the input behind it. | At least one identity in `owner_presented_inputs`. |
| `environment-certified` | Your environment certifies it. | At least one identity in `environment_certificates`. |

A declaration is labelling. It says what you claim, and the conformance suite
refuses only a claim the port contradicts: a capability the port never showed,
an assurance above the plainest one with nothing named to rest it on, a
contract version these ports do not declare, a value of the wrong shape, or a
value carrying something that should never have crossed.

## What must never cross a port

Every plain value an adapter sends across a contract is read for two families
of shape, and a value carrying either is a conformance failure:

- A route to a machine. A lettered volume, a share and its host, a path from
  the root, a written home directory, a climb out of where a name starts, a
  relative path written with a machine path's separator, an address under any
  scheme, and a local file address.
- A written credential. A named secret, a named key, a presented token, the
  opening line of a stored key, a secret written against its name, a user and
  a secret written inside an address, and a token written against the header
  that carries it.

Both families come from one place in this product, so this boundary, the
record boundary and the published-candidate scan all read the same shapes.

The words of a refusal are read the same way. A refusal that repeats the
reference it was given carries whatever that reference held onward into
whatever reads the refusal, so a conforming adapter refuses with words that
name no value at all.

The stored bytes of an evidence record are not read. Those bytes are your
material: the intake workflow digests them and compares, and this product does
not decide what your evidence may say.

## What stays on your side

Locations, credentials, capture, signing, retention and certificate claims are
yours. So is the configuration that tells an adapter where to look. None of it
has a field in any contract here, and none of it belongs in a value, a refusal
or a report.

## Where a digest is checked

The conformance suite reads the **form** of a declared digest and never its
truth. Whether the bytes of a record produce the digest the record claims is
the intake workflow's question, it is asked there for every case, and no
adapter is trusted for it. An adapter declares; the workflow checks.

## Running the conformance suite

Build your adapter over the material the kit carries, hand the surface to the
suite, and read the report.

```python
from evorthon_data.verification.adapters import (
    CONFORMANCE_CANDIDATE,
    CONFORMANCE_DECLARED_OUTPUTS,
    CONFORMANCE_EVIDENCE,
    check_conformance,
)

report = check_conformance(
    candidate_runner=YourRunner(...),
    evidence_repository=YourRepository(...),
)
if not report.conformant:
    for finding in report.findings:
        print(finding.contract, finding.contract_version, finding.member, finding.reason.value, finding.detail)
```

The material is plain values you build your adapter over:
`CONFORMANCE_EVIDENCE` (the records a repository must hold),
`CONFORMANCE_CANDIDATE` (the artefact a runner declares),
`CONFORMANCE_FACTS` with `CONFORMANCE_DECLARED_OUTPUTS` (the case a runner
replays and the outputs it replays for it), and `CONFORMANCE_FOREIGN_FACTS` (a
case nothing is declared against, where either declared outputs or a refusal
is conforming). Pass a runner, a repository, or one of each.

### How a failure reads

Every finding names the port contract it was found against, the version of
that contract, the method or field it was found in, and one reason from a
closed set:

```
EvidenceRepositoryPort evorthon.verification.ports.v1 read_evidence.summary
machine-route-carried the value carries a drive path, and a location stays in
the environment
```

A finding never carries the value it found. A report that repeated an
offending value would carry the leak onward into whatever reads the report,
which is the failure the suite exists to catch.

The closed reasons are `declaration-missing`, `declaration-malformed`,
`contract-version-unknown`, `capability-unknown`, `capability-conflicting`,
`capability-not-observed`, `assurance-unknown`, `assurance-unsupported`,
`value-malformed`, `machine-route-carried`, `credential-carried`,
`contract-not-honoured` and `absence-not-refused`.

## The reference adapters

Four adapters ship with the kit. They are worked examples, they are what the
product is developed against, and each one passes the suite.

- `InMemoryEvidenceRepository` and `InMemoryCandidateRunner` answer from plain
  values handed to their constructors.
- `FixtureEvidenceRepository` and `FixtureCandidateRunner` answer from material
  laid out in a directory you name when you build them.

All four declare `declared` assurance and claim no signing, no retention and no
certificate, because none of that is true of them.

The fixture pair reads a closed layout under the directory you name:

```
evidence/<evidence name>/<version>.content
evidence/<evidence name>/<version>.record.json
candidate.json
declared-outputs/<case name>/<case version>.json
```

Addressing inside it is by logical identity and version, never by a path a
caller supplies. A name is written from letters, digits and the three joining
marks; it does not begin with a stop and carries no climb upward. Anything else
is not a name the layout can hold, so it is refused as not held, and the
refusal says only that. `write_fixture_material` lays plain values out in the
same layout, so what is written and what is read cannot drift apart.

The directory itself is your configuration. It is named once, when you build
the adapter, and it appears in no value that crosses a port, in no refusal and
in no report.

## Writing your own

An adapter of your own needs no change to this product. Implement the contract
you answer, return a declaration that is true, run the suite, and fix what it
finds. If a contradiction the suite reports is not a contradiction in your
environment, that is worth raising: the suite is meant to refuse claims the
port disproves and to leave everything else alone.
