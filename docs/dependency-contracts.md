# Dependency contracts

Evorthon consumes three separately owned delivery mechanisms as published index
distributions: `pinax-tracker`, `autobuild-factory` and `ergasterion-factory`.
It invokes their public commands and reads their published files. It does not
import a sibling source tree, vendor an implementation, or reproduce a tool's
internals.

## Floors, not ceilings

`pyproject.toml` is the sole owner of the delivery version ranges. Each delivery
distribution carries a lower bound and no upper bound. A lower bound names the
first published version that carries an interface Evorthon calls, and it rises
only when Evorthon starts calling a newer interface. Nothing else in the product
restates a range: the adapter contracts in `adapters/` describe the interfaces by
capability and command, and the diagnostics report whatever is installed.

Install the delivery mechanisms only when an adopting delivery needs them:

    pip install 'evorthon-data[delivery]'

The base package and its verification domain work without them.
`evorthon-data diagnose` reads package metadata and reports each delivery
distribution's installed version, or its absence.

## The lock is dated evidence

`uv.lock` records one resolution at one moment. It is build evidence, never a
requirement; the lower bound in `pyproject.toml` is the requirement. Resolved on
2026-09-08 against the public index: `pinax-tracker` 0.1.3, `autobuild-factory`
0.5.0 and `ergasterion-factory` 0.6.1, the last of which newly requires
`sqlglot`.

Refreshing the lock is ordinary maintenance. Re-resolve the three delivery
distributions, run the locked clean-install and adapter-contract checks, and read
the adapter contracts against the newly resolved interfaces. A lower bound moves
only when the code calls a newer interface. An upper bound is never added to hold
a tool back.

## What is not here

The former `local-data` extra is removed. Environment-specific ingestion stays
behind an adopter-owned verification adapter. Teams that need the delivery
distributions migrate to the single `delivery` extra rather than enabling an
ingestion extra on the generator.
