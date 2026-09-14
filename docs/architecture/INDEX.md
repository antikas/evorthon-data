# Architecture

The architecture model lists product components, delivery routes and permitted code dependencies. Start with the readable version to locate the component responsible for a behavior.

- [Component and dependency reference](solution-architecture.md)
- [D2 model](solution-architecture.d2)
- [Architecture diagram](solution-architecture.svg)

The D2 model defines component responsibilities and dependency rules. The Markdown reference and SVG diagram are generated from it. Edit labels and routes in the model, then regenerate both outputs.

Segment readiness is calculated from use-case facts and verification-case identities. It advises on buildable work; it is separate from the Koine method for reviewing intent. The engagement component references verification identities, while verification components hold the cases and results.

The composition component connects the runtime components. Model-access authorization belongs to `security_model_egress`, and shared content patterns belong to `boundary_patterns`. Compatibility wrappers delegate to the engagement implementation.
