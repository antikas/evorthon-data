# Delivery dependencies

Evorthon Data Harness connects to separately released packages for work tracking, builds and generation: `pinax-tracker`, `autobuild-factory` and `ergasterion-factory`. Its adapters call their public commands and read published files. The product uses installed distributions from a package index.

## Version requirements

`pyproject.toml` defines the supported dependency ranges. Each delivery dependency has a minimum version and no upper bound. The minimum is the first published version with an interface Evorthon Data Harness uses; it increases when the product uses a newer interface.

The [adapter contracts](../adapters/) describe capabilities and commands. Version requirements belong in the package metadata, so the contracts do not repeat them.

## Installation and diagnostics

Install the optional delivery tools when an engagement needs them:

```text
python -m pip install "evorthon-data-harness[delivery]"
```

The base package and verification domain work without those tools. Run `evorthon-data-harness diagnose` to report each delivery package's installed version or absence.

Environment-specific ingestion is supplied through the adopting team's verification adapters. The `delivery` extra installs the delivery tools.

## Reproducible builds

`uv.lock` records the exact versions resolved for a build. The minimum supported versions remain in `pyproject.toml`.

When refreshing the lock, resolve the delivery dependencies, run the locked clean-install and adapter-contract checks, and compare the adapter contracts with the resolved interfaces. Keep minimum versions tied to interfaces the product uses, with no upper bounds.
