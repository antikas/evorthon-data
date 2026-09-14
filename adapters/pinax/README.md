# Pinax adapter

Pinax is consumed as the published `pinax-tracker` distribution. The optional
`evorthon_data.delivery.PinaxContractProjector` projects declared use-case scope
through the public `pinax` command. It creates a parent item for each use case
and child items for approved packages, readiness gaps, and span iterations. It
also creates their typed edges and one gap note naming its kind, suggested owner,
and whether synthetic data can fill the gap. Pinax blocks an item until its declared gates are
reached. Pinax records later readiness, claims, completion, and gate resolution.
Evorthon stores opaque returned item identities and reads current state through
the board response. Pinax owns the tracker files.

`contract.md` names every command and option Evorthon uses. `pyproject.toml`
sets the lower bound and `docs/dependency-contracts.md` records the dated
resolution.
