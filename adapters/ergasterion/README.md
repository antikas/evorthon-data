# Ergasterion adapter

Ergasterion is consumed as the published `ergasterion-factory` distribution and
may generate only declared artefacts.

`contract.md` names every command, declaration key, output file, and schema
Evorthon uses. Install the optional distribution through the `delivery` extra
when an adopting delivery generates artefacts. `pyproject.toml` sets the lower
bound and `uv.lock` records resolved versions; `docs/dependency-contracts.md` explains the version policy.
