from pathlib import Path

from evorthon_data.runtime_adapters import adapter_files, validate_runtime_adapters


def test_every_runtime_adapter_class_resolves_to_a_contained_existing_target():
    root = Path(__file__).parents[2].resolve()
    assert len(adapter_files(root)) >= 20
    assert validate_runtime_adapters(root) == []
