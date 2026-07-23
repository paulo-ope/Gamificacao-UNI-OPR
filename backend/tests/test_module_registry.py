from app.modules.registry import get_module, list_modules


def test_module_registry_has_unique_stable_keys_and_paths():
    modules = list_modules()

    assert len({module.key for module in modules}) == len(modules)
    assert len({module.web_path for module in modules}) == len(modules)
    assert all(module.web_path.startswith("/") for module in modules)
    assert all(module.api_prefix.startswith("/api") for module in modules)


def test_operations_module_is_registered_and_active_after_mvp_foundation():
    operations = get_module("operations")

    assert operations is not None
    assert operations.status == "active"
    assert operations.required_permission == "operations:read"
