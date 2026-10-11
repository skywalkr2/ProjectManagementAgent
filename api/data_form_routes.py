"""API routes for editing a plugin's data files through forms (plugin API 0.3.52): the kinds running plugins declare,
the files of a kind across the data layers, one file as a form, and saving, removing and undoing a layered copy."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import (
    DataFile,
    DataFileChange,
    DataFileRestore,
    DataFileSaved,
    DataFileView,
    DataFormView,
    SettingItem,
)
from engine import data_forms
from engine.settings import _walk
from engine.storage import Store, StoreError


def build_data_form_router(store: Store) -> APIRouter:
    r = APIRouter(prefix="/api")
    host = store.plugins

    def guard(fn):  # noqa: ANN001, ANN202 - a refusal is the person's to read
        try:
            return fn()
        except StoreError as err:
            raise HTTPException(status_code=409, detail=str(err)) from None

    @r.get("/data-forms")
    def forms() -> list[DataFormView]:
        """The kinds of data file running add-ons let the person edit through a form."""
        return [
            DataFormView(name=f.name, plugin=plugin, label=f.label, description=f.description)
            for plugin, registrar in sorted(host.registrars.items())
            if host.active(plugin)
            for f in registrar.data_forms.values()
        ]

    @r.get("/data-forms/{name:path}/files")
    def files(name: str, project: str | None = None) -> list[DataFile]:
        return [DataFile(**f) for f in guard(lambda: data_forms.files(host, name, project))]

    @r.get("/data-forms/{name:path}/file")
    def file(name: str, path: str, project: str | None = None) -> DataFileView:
        """One file as a form: its fields (from the schema) with the values in effect, and the layer they come from;
        a file that doesn't exist yet shows the schema's defaults."""
        found = guard(lambda: data_forms.read(host, name, path, project))
        form = guard(lambda: data_forms._form(host, name))
        items: list = []
        _walk(form.schema, ["form"], found["values"] or found["defaults"], found["defaults"], {}, items)
        for item in items:
            item.key = item.key.removeprefix("form.")
            item.group = item.group.removeprefix("form.").removeprefix("form")
            item.file = path
            item.source = "file" if found["layer"] else "default"
        return DataFileView(
            file=path,
            layer=found["layer"],
            layers=found["layers"],
            problem=found["problem"],
            items=[SettingItem(**vars(i)) for i in items],
        )

    @r.post("/data-forms/{name:path}/file")
    def save(name: str, body: DataFileChange) -> DataFileSaved:
        """Save the workspace's or a project's copy with these changes, checked against the schema; `before` undoes."""
        done = guard(lambda: data_forms.save(host, name, body.file, body.layer, body.changes, body.project))
        return DataFileSaved(before=done["before"])

    @r.post("/data-forms/{name:path}/remove")
    def remove(name: str, body: DataFileChange) -> DataFileSaved:
        """Remove the workspace's or a project's copy; the less specific one is in effect again."""
        done = guard(lambda: data_forms.remove(host, name, body.file, body.layer, body.project))
        return DataFileSaved(before=done["before"])

    @r.post("/data-forms/{name:path}/restore")
    def restore(name: str, body: DataFileRestore) -> DataFileSaved:
        """Undo a save or a removal: the layer's copy as it was before."""
        guard(lambda: data_forms.restore(host, name, body.file, body.layer, body.before, body.project))
        return DataFileSaved(before=None)

    return r
