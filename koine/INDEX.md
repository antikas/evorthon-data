# Koine data co-worker
<!-- evorthon-implements: EVD-README-032 -->

The coworker pack contains delivery prompts, reviewers and record templates. They follow the runtime engagement and verification contracts described in the [architecture reference](../docs/architecture/solution-architecture.md). The runtime defines lifecycle, verification and model-access behavior.

Validation checks template fields, structured success criteria, generator/reviewer pairs, runtime adapters and generator references.

The use-case intake route is artefact-first. It reads schemas, extracts, transformations, reports, schedules and catalogue exports already available to the team. It records each fact with its artefact and extraction method, asks only questions that artefacts cannot answer, and proposes no parser for an artefact shape.

- [Method](method/INDEX.md)
- [Templates](templates/)
- [Skills](skills/)
