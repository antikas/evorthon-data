"""Public distribution capability inspection without source-path coupling."""
# evorthon-implements: EVD-README-033
# evorthon-implements: EVD-README-034
# evorthon-component: composition
from importlib.metadata import PackageNotFoundError, version

DELIVERY_DISTRIBUTIONS = ("pinax-tracker", "autobuild-factory", "ergasterion-factory")

def installed_capabilities():
    result = {}
    for distribution in DELIVERY_DISTRIBUTIONS:
        try:
            result[distribution] = {"installed": True, "version": version(distribution)}
        except PackageNotFoundError:
            result[distribution] = {"installed": False, "version": None}
    return result
