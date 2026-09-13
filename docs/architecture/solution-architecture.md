# Evorthon Data architecture

Direction: `down`.

## Components

- `intent` - Human intent and platform evidence
- `koine_projection` - Koine projections: validated Markdown, templates, prompts and reviews
- `engagement` - Engagement lifecycle, the use-case aggregate and named human decisions; verification identities only
- `readiness` - per-segment buildability computed from use-case facts and case identities; advice, never a gate; distinct from the Koine intent-readiness discipline
- `synthetic` - labelled frozen datasets generated from declared shape and constraints
- `verification_domain` - Verification domain: cases, results, proposals and identities
- `verification_core` - Verification core: portable deterministic semantics
- `verification_enforcement` - Verification enforcement: schemas and fail-closed policy
- `verification_workflows` - Verification workflows: intake, reconciliation and diagnosis orchestration
- `verification_ports` - Verification ports: environment-owned access contracts
- `verification_adapters` - Verification adapters: adopter-owned environment implementations
- `verification_presentation` - Verification presentation: safe CLI, records and review surfaces
- `security_model_egress` - security/model_egress: sole authorization and enforcement owner
- `boundary_patterns` - Boundary patterns: the closed shapes for machine routes, credentials and raw rows, one owner and no other content
- `composition` - Composition root: product wiring without domain ownership
- `delivery_adapters` - Narrow adapters for opt-in released delivery wheels
- `pinax` - Pinax released wheel: live work graph
- `ergasterion` - Ergasterion released wheel: declared generation
- `autobuild` - AutoBuild released wheel: approved engineering
- `presentation` - Product presentation and dependency diagnostics
- `compatibility` - Temporary compatibility facades with no semantic ownership
- `human_acceptance` - Named human acceptance and durable learning

## Routes

- `intent -> koine_projection`
- `koine_projection -> engagement`
- `engagement -> verification_domain`
- `engagement -> composition`
- `composition -> delivery_adapters`
- `composition -> readiness`
- `readiness -> verification_domain`
- `composition -> synthetic`
- `synthetic -> verification_domain`
- `delivery_adapters -> pinax`
- `delivery_adapters -> ergasterion`
- `delivery_adapters -> autobuild`
- `verification_domain -> verification_core`
- `verification_domain -> verification_enforcement`
- `verification_core -> verification_workflows`
- `verification_enforcement -> verification_workflows`
- `verification_adapters -> verification_ports`
- `verification_ports -> verification_workflows`
- `koine_projection -> security_model_egress`
- `verification_workflows -> security_model_egress`
- `verification_workflows -> verification_presentation`
- `verification_presentation -> human_acceptance`
- `engagement -> human_acceptance`

## Direct dependency policy

Direct imports between product components are deny-by-default: every cross-component import not listed as allowed is forbidden.

### Allowed direct dependencies

- `compatibility -> engagement`
- `composition -> delivery_adapters`
- `composition -> engagement`
- `composition -> koine_projection`
- `composition -> readiness`
- `composition -> synthetic`
- `composition -> verification_adapters`
- `composition -> verification_domain`
- `composition -> verification_enforcement`
- `composition -> verification_presentation`
- `composition -> verification_workflows`
- `delivery_adapters -> autobuild`
- `delivery_adapters -> boundary_patterns`
- `delivery_adapters -> engagement`
- `delivery_adapters -> ergasterion`
- `delivery_adapters -> pinax`
- `delivery_adapters -> readiness`
- `delivery_adapters -> verification_domain`
- `delivery_adapters -> verification_workflows`
- `engagement -> boundary_patterns`
- `engagement -> verification_domain`
- `koine_projection -> boundary_patterns`
- `koine_projection -> engagement`
- `koine_projection -> security_model_egress`
- `presentation -> boundary_patterns`
- `presentation -> composition`
- `presentation -> engagement`
- `presentation -> readiness`
- `presentation -> verification_presentation`
- `readiness -> engagement`
- `readiness -> verification_domain`
- `synthetic -> verification_core`
- `synthetic -> verification_domain`
- `verification_adapters -> boundary_patterns`
- `verification_adapters -> verification_ports`
- `verification_core -> verification_domain`
- `verification_enforcement -> boundary_patterns`
- `verification_enforcement -> verification_domain`
- `verification_presentation -> engagement`
- `verification_presentation -> verification_domain`
- `verification_presentation -> verification_workflows`
- `verification_workflows -> security_model_egress`
- `verification_workflows -> verification_core`
- `verification_workflows -> verification_domain`
- `verification_workflows -> verification_enforcement`
- `verification_workflows -> verification_ports`

### Explicitly protected boundaries

- `delivery_adapters -> verification_core`
- `engagement -> verification_core`
- `koine_projection -> verification_core`
- `presentation -> verification_core`
- `readiness -> verification_core`
- `readiness -> verification_enforcement`
- `readiness -> verification_workflows`
- `security_model_egress -> engagement`
- `synthetic -> engagement`
- `verification_adapters -> verification_workflows`
- `verification_core -> verification_adapters`
- `verification_domain -> engagement`
- `verification_workflows -> delivery_adapters`
