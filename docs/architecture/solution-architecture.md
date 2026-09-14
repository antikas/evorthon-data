# Evorthon Data Harness architecture

Direction: `down`.

## Components

- `intent` - Human decisions and platform evidence
- `koine_projection` - Validated Markdown records, templates, prompts and reviews
- `engagement` - Engagement lifecycle, use-case records and named human decisions; verification identities only
- `readiness` - Per-segment buildability from use-case facts and case identities; advisory; separate from the Koine intent-readiness method
- `synthetic` - Labelled frozen datasets generated from declared shape and constraints
- `verification_domain` - Verification cases, results, proposals and identities
- `verification_core` - Portable deterministic verification rules
- `verification_enforcement` - Schema checks and fail-closed policy
- `verification_workflows` - Verification intake, reconciliation and diagnostic workflows
- `verification_ports` - Environment-owned access contracts
- `verification_adapters` - Adopter-owned environment implementations
- `verification_presentation` - Verification commands, safe records and review outputs
- `security_model_egress` - Sole owner of model access authorization and enforcement
- `boundary_patterns` - Sole owner of closed machine-route, credential and raw-row patterns
- `composition` - Connects product components; each component owns its behavior
- `delivery_adapters` - Narrow adapters to optional released delivery distributions
- `pinax` - Pinax: shared work tracking
- `ergasterion` - Ergasterion: contract-based generation
- `autobuild` - AutoBuild: approved build work
- `presentation` - Product commands and diagnostics
- `compatibility` - Temporary compatibility wrappers; behavior delegated to components
- `human_acceptance` - Named human acceptance and recorded learning

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
