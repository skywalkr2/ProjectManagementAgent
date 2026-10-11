"""The plugin developer guide is generated from the code and covers the whole public API."""

import engine.plugin_api as api
from engine.plugin_guide import build
from engine.plugin_host import EVENT_SPECS
from engine.plugin_manifest import NOT_YET


def test_the_guide_names_every_public_item_event_and_unavailable_key():
    guide = build()
    for name in api.__all__:
        assert f"`{name}`" in guide, name
    for event in EVENT_SPECS:
        assert f"### `{event}`" in guide, event
    for key in NOT_YET:
        assert f"`{key}`" in guide, key
    assert f"Plugin API **{api.PLUGIN_API_VERSION}**" in guide


def test_every_registrar_method_is_documented():
    guide = build()
    for name, member in vars(api.Registrar).items():
        if callable(member) and not name.startswith("_"):
            assert member.__doc__, f"Registrar.{name} needs a docstring: the guide is generated from it"
            assert f"`registrar.{name}(" in guide


def test_record_set_docs_name_every_field_it_may_change():
    # The docstring reaches the assistant and the guide; it must list exactly what the applier allows.
    from engine.ops import SETTABLE, RecordSetOp

    for kind, fields in SETTABLE.items():
        for name in fields:
            assert name in RecordSetOp.__doc__, (kind, name)
