# Incident containment for a published artefact

## What this page is

This is the supervised runbook for the case where something already published
turns out to be wrong, unsafe, or not what it claimed to be. Published means it
has left this repository: a package version on an index, a tagged public tree,
a downloadable artefact, or a document that named any of them.

Every step below is performed by a named person and recorded. Nothing on this
page runs automatically, and no tool in this product performs any of it. The
product has no command that withdraws, deletes, overwrites or notifies, and
none is automated: containment touches other people's copies of an artefact, so
it is a human decision each time, taken with the evidence in front of the
person taking it.

Read the whole page before starting. The order matters: stopping the spread
comes before deciding what to withdraw, and preserving the evidence comes
before anything that changes it.

## The named people

Three roles carry the decisions. One person may hold more than one role in a
small team, but each decision is recorded against the role that owned it.

| Role | What this role decides |
|---|---|
| Owner | Whether an incident is open, what is withdrawn, who is told, and when the incident is closed. |
| Responder | How containment is carried out, and what is recorded about it. |
| Reviewer | Whether the evidence supports the owner's decision, stated before the decision is taken. |

The owner is the only role that may decide to withdraw a published artefact or
to tell anyone outside the team. The responder never makes that call alone, and
never makes it because a check failed.

## What opens an incident

An incident is open when the owner says it is. Anything below is a reason to
ask the owner, not a reason to act:

- A published artefact carries material that should not have left the private
  tree: real data, a credential, an internal address, a machine path, or a name
  belonging to someone else.
- A published artefact does not match the identity it claims: its digest, its
  source commit, its inventory or its licence disagree with what was published
  beside it.
- A published artefact behaves in a way that could damage the person running
  it, or produces evidence that would mislead them.
- A dependency or a signing identity used to produce a published artefact is
  reported compromised.

## 1. Halt

Purpose: stop anything that would produce, publish or promote another copy
while the facts are unknown.

The responder:

1. Stops every automated job that could publish, tag or upload. Stopping means
   disabling the trigger, not deleting the job.
2. Stops any work in progress that would produce a new candidate from the same
   source, and says so in the team's working channel.
3. Records the time of the halt and what was stopped.

Decision point (owner): confirm the halt, or lift it if the report is a false
alarm. Record which, with the reason.

Nothing is withdrawn at this step. A halt is reversible; a withdrawal is not.

## 2. Quarantine

Purpose: separate the affected artefact and everything that describes it, so
the facts can be established without anyone changing them.

The responder:

1. Copies the published artefact exactly as it stands, with its digest, its
   published inventory, its metadata and the page or index entry that offered
   it. The copy is read-only from that moment.
2. Copies the private evidence that produced it: the source commit identity,
   the built artefact hash, the verdict artefacts, the review outcomes and the
   candidate inventory.
3. Marks the affected artefact internally as under investigation, so nobody in
   the team promotes, links to or builds on it.
4. Records what was copied, where it is held, and who can read it.

Decision point (owner): confirm the scope. Name every version, tag and artefact
that is in scope, and every one that has been checked and is out of scope. A
version nobody has checked is in scope until somebody checks it.

Quarantine changes nothing that is published. It only makes a fixed copy and
marks the internal state.

## 3. Yank and revoke

Purpose: stop new consumers from taking the affected artefact, and stop any
identity that could sign or publish another one.

This step changes what other people can get. It happens only on a recorded
owner decision, with the reviewer's statement about the evidence already on
record.

The responder, once the owner has decided:

1. Yanks the affected package version on the index. Yanking leaves the version
   installable for a pinned dependency that already names it and stops it being
   chosen for anything new. Prefer yanking to deleting: deleting destroys the
   evidence other people hold and breaks builds that already depend on it.
2. Removes or supersedes the public page, tag or link that offered it, keeping
   the quarantined copy of what was there.
3. Revokes any credential, token or signing identity that the incident implicates,
   and records the new identity that replaces it.
4. Records each action, the time, and the person who performed it.

Decision point (owner): take each of the following separately, and record each
one with its reason.

- Yank, delete, or leave in place. Deletion is the last resort and needs a
  stated reason why yanking is not enough.
- Revoke each named identity, or keep it.
- Publish a superseding version now, or wait until the cause is understood.

## 4. Notification

Purpose: tell the people who need to know, in the order that serves them, with
what is known and what is not.

The owner decides who is told, what they are told, and when. The responder
drafts; the owner approves the wording before anything is sent.

Order:

1. The team, at the moment the incident opens.
2. Anyone contractually or legally entitled to be told, within the time their
   agreement or the applicable law states. If personal data may have left the
   private tree, the owner establishes that deadline before anything else in
   this step.
3. Known consumers of the affected artefact.
4. The public record beside the artefact, once the first three are done.

Every notice states what happened, which versions are affected, what a reader
should do now, what is still unknown, and who to contact. It never states a
cause that has not been established, and it never blames a named individual.

Decision point (owner): approve each notice before it is sent, and record the
approved text with the time it went out.

## 5. Preserved forensics

Purpose: keep enough evidence to explain the incident afterwards, and to prove
what was done about it.

The responder preserves, unchanged:

- The quarantined copy of the published artefact and everything published
  beside it.
- The private evidence bundle for the accepted commit the artefact came from:
  verdicts, reviews, inventories, the built artefact hash.
- The index and page state before and after each withdrawal, captured at the
  time.
- The log of every action in this runbook, with times, roles and names.
- Every approved notice, as sent.

Nothing preserved is edited afterwards. A correction is a new record beside the
old one, never a change to it. If a preserved item has to be held somewhere the
team does not control, the owner records where and why.

Decision point (owner): confirm the preserved set is complete before the
incident is closed. An incomplete set keeps the incident open.

## Closing

The owner closes the incident with a short record naming: what happened, which
artefacts were affected, what was withdrawn or revoked, who was told, what the
cause was or that it is still unknown, and what changes to the product or the
publication gate follow from it. Work that follows from an incident is tracked
like any other work and is not part of this runbook.

## What this runbook never does

- It never acts without a named person deciding.
- It never lets a tool withdraw, delete, overwrite or notify on its own.
- It never deletes evidence, including evidence that is inconvenient.
- It never states a cause that has not been established.
- It never treats a failed check as an incident by itself. A failed check is
  a reason to ask the owner.
