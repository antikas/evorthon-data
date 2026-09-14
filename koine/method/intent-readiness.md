# Intent readiness

Readiness identifies work that can proceed with recorded facts and declared fallbacks. It is recomputed per segment.

## Readiness assessment

1. **Read the artefacts.** Take what the team already has and read it with base tools, following [artefact-first intake](artefact-first-intake.md).
2. **Record the facts.** Write each value into the intake record with its artefact identity, its position inside that artefact, its extractor and a status of extracted, inferred or confirmed. Put the whole pass of inferences to a human as one bulk confirmation.
3. **Recompute readiness per segment.** A segment runs from its sources to the next checkpoint or target output. Assess each segment against its required facts and declared fallbacks. A ready segment proceeds when another segment lacks facts.
4. **Show readiness.** List buildable work and its fallbacks, gaps with suggested owners and synthetic-data eligibility, and open questions that no artefact answered.
5. **Ask the residual questions.** Ask only residual questions. Record "I do not know yet" as an answer that creates a gap.
6. **Repeat.** The human decides what to obtain, what to synthesise and what to leave. Accepted gap work becomes tracked items. A use case already in build re-enters the loop when a new output or scenario appears, and that starts a new version.

## Readiness rules

Readiness reports available work and gaps for a human decision. Label synthetic data and record its limits against real-data parity. An unanswered standing condition records its default. Inferred facts remain marked inferred until a human confirms them. Fact provenance informs the human decision and does not refuse work.
