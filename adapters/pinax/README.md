# Pinax adapter

Pinax is consumed as the published `pinax-tracker` distribution. The optional
`evorthon_data.delivery.PinaxContractProjector` projects declared use-case scope
through the public `pinax` command: one parent item for each use case, one child
item for each approved package, each readiness gap and each iteration on a span,
the typed edges between them, and one note on each gap item naming the gap kind,
the suggested owner and whether synthetic data can fill it. An item the declared
gates have not yet reached starts blocked with Pinax; only Pinax records any
later readiness, claims, completion or gate resolution. Evorthon stores opaque
returned item identities, not tracker state, reads folded state back through the
board response, and never reads or writes a tracker file.

`contract.md` beside this file names every command and option Evorthon uses. No
version is named here; `pyproject.toml` owns the lower bound and
`docs/dependency-contracts.md` records the dated resolution.
