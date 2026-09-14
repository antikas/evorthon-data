# Published-artefact incidents

Use this procedure when a published package, tagged tree, download or related document contains unsafe material, behaves incorrectly or differs from its declared identity. All actions require named people; nothing on this page runs automatically.

Withdrawal, deletion, overwriting and notification require an explicit owner decision. Product tools do not perform these actions automatically. Halt further publication and preserve the evidence before changing any published artefact.

## Responsibilities

One person may hold several roles, but each decision records the role responsible for it.

| Role | Responsibility |
| --- | --- |
| Owner | Opens and closes the incident; decides what to withdraw and who to notify. |
| Responder | Performs approved containment actions and records them. |
| Reviewer | Assesses whether the evidence supports a proposed owner decision before it is taken. |

## Incident reports

Report the following conditions to the owner:

- Published material includes private data, credentials, internal addresses, machine paths or another party's protected information.
- A published artefact disagrees with its declared digest, source commit, inventory or licence.
- Its behavior could harm users or produce misleading evidence.
- A dependency or signing identity used for publication is reported compromised.

The owner decides whether to open an incident. A failed check alone does not authorize containment actions.

## 1. Halt

The responder stops further production and publication while the report is assessed:

1. Disable triggers for jobs that could publish, tag or upload. Keep the job definitions.
2. Stop work that could produce another candidate from the affected source and inform the team.
3. Record the halt time and the work stopped.

Decision point (owner): confirm the halt, or lift it with a recorded reason if the report is a false alarm. This step leaves published artefacts in place.

## 2. Quarantine

The responder preserves a fixed copy for investigation:

1. Copy the published artefact, digest, inventory, metadata and page or index entry. Keep that copy read-only.
2. Copy the source commit identity, built artefact hash, verdicts, review outcomes and candidate inventory from the private publication evidence.
3. Mark the affected artefact internally as under investigation. Prevent the team from promoting, linking to or building on it.
4. Record what was copied, its storage location and who can access it.

Decision point (owner): name every affected version, tag and artefact, plus those checked and excluded. Keep unchecked versions in scope until they are assessed. Quarantine preserves copies and changes internal status; it leaves the publication unchanged.

## 3. Yank and revoke

The reviewer records an assessment of the evidence before the owner decides on withdrawal or revocation.

Once authorized, the responder:

1. Yanks affected package versions on the index. Prefer yanking to deleting: yanking retains the version for existing exact pins while preventing normal selection for new dependencies. Deletion can break builds and remove access to publication evidence.
2. Removes or supersedes affected public pages, tags or links, retaining their quarantined copies.
3. Revokes implicated credentials, tokens or signing identities and records their replacements.
4. Records each action, time and responsible person.

Decision point (owner): record each decision and its reason:

- Yank, delete or leave each affected artefact in place. Deletion requires an explanation of why yanking is insufficient.
- Revoke or retain each implicated identity.
- Publish a corrected version or wait until the cause is established.

## 4. Notification

The responder drafts notices. The owner approves recipients, content and timing before any notice is sent.

Notify in this order:

1. The team when the incident opens.
2. People or organisations entitled to notification under an agreement or applicable law, within the relevant deadline. If personal data may have been disclosed, the owner establishes that deadline before proceeding with this step.
3. Known consumers of the affected artefact.
4. Readers of the public record beside the artefact, after the preceding notices.

Each notice states the event, affected versions, required user action, unresolved questions and contact details. State only established causes and avoid attributing blame to individuals.

Decision point (owner): approve each notice before sending, then retain its exact text and sending time.

## 5. Preserved forensics

Preserve evidence unchanged, including:

- The quarantined artefact and accompanying published material.
- The accepted private commit's verdicts, reviews, inventories and built artefact hash.
- The index and page state before and after withdrawal.
- The action log with times, roles and names.
- Every approved notice as sent.

Add corrections as separate records. If evidence must be held outside the team's control, the owner records where and why.

Decision point (owner): verify that the evidence set is complete before closing the incident. Missing evidence keeps the incident open.

## Closure

The owner records the event, affected artefacts, withdrawals, revocations and notifications. Include the established cause or remaining uncertainty, plus changes required to the product or publication procedure. Register follow-up work in the tracker.
