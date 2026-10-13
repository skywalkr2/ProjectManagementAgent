"""Installing an add-on from the Add-ons screen: the release file the catalog names is downloaded, checked against its
checksum, and installed only when it is pure Python whose needs the app already has; removing takes away only what
was installed from here."""

import hashlib
import io
import zipfile

import httpx
import pytest

from engine import pack_install
from engine.pack_install import InstallError

WEB = "https" + "://"
RELEASE = f"{WEB}releases.example.com/p/pack-0.1.0-py3-none-any.whl"


def wheel(name="pack-demo", tag="py3-none-any", purelib="true", requires=(), extra=None):
    buffer = io.BytesIO()
    info = f"{name.replace('-', '_')}-0.1.0.dist-info"
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("pack_demo/__init__.py", "def register(registrar):\n    pass\n")
        meta = f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1.0\n"
        meta += "".join(f"Requires-Dist: {r}\n" for r in requires)
        z.writestr(f"{info}/METADATA", meta)
        z.writestr(f"{info}/WHEEL", f"Wheel-Version: 1.0\nRoot-Is-Purelib: {purelib}\nTag: {tag}\n")
        z.writestr(f"{info}/entry_points.txt", "[pm_cockpit.plugins]\npackdemo = pack_demo:register\n")
        z.writestr(f"{info}/RECORD", "")
        for path, text in (extra or {}).items():
            z.writestr(path, text)
    return buffer.getvalue()


def test_a_pure_python_pack_installs_and_removes(tmp_path):
    done = pack_install.install(wheel(), tmp_path)
    assert (done.name, done.version) == ("pack-demo", "0.1.0")
    assert (tmp_path / "pack_demo" / "__init__.py").is_file()
    assert (tmp_path / "pack_demo-0.1.0.dist-info" / "INSTALLER").read_text().strip() == "pm-cockpit"
    again = pack_install.install(wheel(), tmp_path)  # an update replaces the earlier install
    assert again.files == done.files
    pack_install.remove("pack-demo", tmp_path)
    assert not (tmp_path / "pack_demo").exists() and not list(tmp_path.glob("*.dist-info"))


def test_removing_a_pack_that_ran_leaves_nothing_of_it_behind(tmp_path):
    """Python writes compiled copies of a pack's files beside them once the app has run it; they aren't in the pack's
    record, and the package folder must still go, while another pack's compiled files stay."""
    pack_install.install(wheel(), tmp_path)
    (tmp_path / "pack_demo" / "__pycache__").mkdir()
    (tmp_path / "pack_demo" / "__pycache__" / "__init__.cpython-312.pyc").write_bytes(b"compiled")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "other.cpython-312.pyc").write_bytes(b"compiled")
    pack_install.remove("pack-demo", tmp_path)
    assert not (tmp_path / "pack_demo").exists() and not list(tmp_path.glob("*.dist-info"))
    assert (tmp_path / "__pycache__" / "other.cpython-312.pyc").is_file()


@pytest.mark.parametrize(
    "data, problem",
    [
        (wheel(tag="cp312-cp312-linux_x86_64"), "pure Python"),
        (wheel(purelib="false"), "pure Python"),
        (wheel(requires=["a-package-nobody-has>=1"]), "a-package-nobody-has"),
        (wheel(extra={"../escape.py": "x"}), "paths"),
        (wheel(extra={"pack_demo-0.1.0.data/scripts/run": "x"}), "paths"),
        (b"not a zip", "isn't a package"),
    ],
    # Named, not derived from the bytes: a zip carries its build time, which would change the ids between workers.
    ids=["compiled", "not-purelib", "missing-requirement", "escaping-path", "data-script", "not-a-zip"],
)
def test_what_cant_be_installed_from_here_is_refused(tmp_path, data, problem):
    with pytest.raises(InstallError, match=problem):
        pack_install.install(data, tmp_path)
    assert not (tmp_path / "pack_demo").exists()


def test_a_pack_installed_another_way_is_left_alone(tmp_path):
    pack_install.install(wheel(), tmp_path)
    (tmp_path / "pack_demo-0.1.0.dist-info" / "INSTALLER").write_text("pip\n")
    with pytest.raises(InstallError, match="another way"):
        pack_install.remove("pack-demo", tmp_path)
    with pytest.raises(InstallError, match="another way"):
        pack_install.install(wheel(), tmp_path)


def test_the_download_must_match_the_checksum_and_a_token_stays_with_its_host():
    data = wheel()
    seen = []

    def service(request):
        seen.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "releases.example.com":
            return httpx.Response(302, headers={"location": f"{WEB}files.example.com/blob"})
        return httpx.Response(200, content=data)

    client = httpx.Client(transport=httpx.MockTransport(service), follow_redirects=True)
    got = pack_install.download(RELEASE, hashlib.sha256(data).hexdigest(), token="t0ken", client=client)
    assert got == data
    assert seen == [("releases.example.com", "Bearer t0ken"), ("files.example.com", None)]
    with pytest.raises(InstallError, match="checksum"):
        pack_install.download(RELEASE, "0" * 64, client=client)
    refused = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(InstallError, match="read token"):
        pack_install.download(RELEASE, "0" * 64, client=refused)


def test_the_install_route_uses_the_catalog_entry(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine import packs
    from tests.test_setup import make

    data = wheel()
    entry = packs.Entry(
        id="packdemo",
        name="Pack demo",
        release={"url": RELEASE, "sha256": hashlib.sha256(data).hexdigest()},
    )
    bare = packs.Entry(id="bare", name="Bare", install="Ask the publisher.")
    monkeypatch.setattr(packs, "read_feeds", lambda *a, **k: [packs.Feed(RELEASE, [entry, bare])])
    monkeypatch.setattr(pack_install, "download", lambda url, sha, token=None, client=None: data)
    place = tmp_path / "site"
    place.mkdir()
    monkeypatch.setattr(pack_install, "target", lambda: place)
    ws, cfg, store = make(tmp_path)
    store.close()
    c = TestClient(create_app(ws, cfg, "t", start_worker=False))
    c.headers["Authorization"] = "Bearer t"
    api = cfg.server.base_path.rstrip("/") + "/api"
    listed = {p["id"]: p for p in c.get(f"{api}/packs").json()["available"]}
    assert listed["packdemo"]["installable"] and not listed["bare"]["installable"]
    done = c.post(f"{api}/packs/packdemo/install")
    assert done.status_code == 200, done.text
    assert done.json() == {"name": "pack-demo", "version": "0.1.0", "needs_restart": True}
    assert (place / "pack_demo" / "__init__.py").is_file()
    assert c.post(f"{api}/packs/bare/install").status_code == 409
    assert c.post(f"{api}/packs/nothing/install").status_code == 404


@pytest.fixture
def screen(tmp_path, monkeypatch):
    """The app with a catalog listing one installable add-on, the download faked, and a folder to install into."""
    from fastapi.testclient import TestClient

    from api.app import create_app
    from engine import packs
    from tests.test_setup import make

    data = wheel()
    entry = packs.Entry(
        id="packdemo",
        name="Pack demo",
        release={"url": RELEASE, "sha256": hashlib.sha256(data).hexdigest()},
    )
    monkeypatch.setattr(packs, "read_feeds", lambda *a, **k: [packs.Feed(RELEASE, [entry])])
    monkeypatch.setattr(pack_install, "download", lambda url, sha, token=None, client=None: data)
    place = tmp_path / "site"
    place.mkdir()
    monkeypatch.setattr(pack_install, "target", lambda: place)
    monkeypatch.syspath_prepend(str(place))
    ws, cfg, store = make(tmp_path)
    store.close()
    app = create_app(ws, cfg, "t", start_worker=False)
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer t"
    return c, cfg.server.base_path.rstrip("/") + "/api", app.state.worker, place


def test_installing_an_add_on_that_isnt_running_holds_no_work(screen):
    c, api, worker, _ = screen
    assert worker.restart_needed is None and worker.restart_for == []
    done = c.post(f"{api}/packs/packdemo/install")
    assert done.status_code == 200 and done.json()["needs_restart"] is True  # the row offers Restart now
    assert worker.restart_needed is None and worker.restart_for == []  # but nothing the app runs changed
    assert c.get(f"{api}/packs").json()["available"][0]["removable"] is True


def test_updating_an_add_on_that_is_running_waits_for_a_restart(screen, monkeypatch):
    c, api, worker, _ = screen
    monkeypatch.setattr(type(worker.store.plugins), "active", lambda self, name: name == "packdemo")
    assert c.post(f"{api}/packs/packdemo/install").status_code == 200
    assert worker.restart_needed and worker.restart_for == ["add-ons"]
    status = c.get(f"{api}/status").json()
    assert status["restart_needed"] and status["restart_for"] == ["add-ons"]


def test_removing_an_add_on_the_app_installed_holds_no_work(screen):
    c, api, worker, place = screen
    c.post(f"{api}/packs/packdemo/install")
    done = c.post(f"{api}/packs/packdemo/uninstall")
    assert done.status_code == 200, done.text
    assert done.json()["needs_restart"] is True
    assert not (place / "pack_demo").exists()
    assert worker.restart_needed is None and worker.restart_for == []
    assert c.get(f"{api}/packs").json()["available"][0]["removable"] is False


def test_an_add_on_the_app_didnt_install_is_not_removed_from_the_screen(screen):
    c, api, worker, place = screen
    c.post(f"{api}/packs/packdemo/install")
    (place / "pack_demo-0.1.0.dist-info" / "INSTALLER").write_text("pip\n")
    worker.restart_needed, worker.restart_for = None, []
    assert c.get(f"{api}/packs").json()["available"][0]["removable"] is False
    refused = c.post(f"{api}/packs/packdemo/uninstall")
    assert refused.status_code == 409 and "another way" in refused.json()["detail"]
    assert (place / "pack_demo" / "__init__.py").is_file()
    assert worker.restart_needed is None and worker.restart_for == []


def test_a_refused_install_says_why_in_a_sentence_and_marks_no_restart(screen, monkeypatch):
    c, api, worker, _ = screen

    def refuse(*args, **kwargs):
        raise InstallError("the file doesn't match")

    monkeypatch.setattr(pack_install, "download", refuse)
    refused = c.post(f"{api}/packs/packdemo/install")
    assert refused.status_code == 409 and refused.json()["detail"] == "The file doesn't match."
    assert worker.restart_needed is None


def test_an_add_on_turned_off_but_still_running_can_be_removed_and_work_waits_for_the_restart(screen, monkeypatch):
    c, api, worker, place = screen
    c.post(f"{api}/packs/packdemo/install")
    # Turned off in the saved settings, but this process still runs it until the restart.
    monkeypatch.setattr(type(worker.store.plugins), "active", lambda self, name: name == "packdemo")
    done = c.post(f"{api}/packs/packdemo/uninstall")
    assert done.status_code == 200, done.text
    assert not (place / "pack_demo").exists()
    assert worker.restart_needed and worker.restart_for == ["add-ons"]


def test_an_add_on_still_on_in_the_saved_settings_is_not_removed(screen):
    import yaml

    c, api, worker, place = screen
    c.post(f"{api}/packs/packdemo/install")
    path = worker.ws.config_dir / "workspace.yaml"
    data = yaml.safe_load(path.read_text())
    data.setdefault("plugins", {})["enabled"] = [*data.get("plugins", {}).get("enabled", []), "packdemo"]
    path.write_text(yaml.safe_dump(data))
    refused = c.post(f"{api}/packs/packdemo/uninstall")
    assert refused.status_code == 409 and "Turn it off first" in refused.json()["detail"]
    assert (place / "pack_demo" / "__init__.py").is_file()


def test_the_install_command_puts_an_add_on_file_in_place(tmp_path, monkeypatch, capsys):
    from engine.cli import main

    place = tmp_path / "site"
    place.mkdir()
    monkeypatch.setattr(pack_install, "target", lambda: place)
    file = tmp_path / "pack_demo-0.1.0-py3-none-any.whl"
    file.write_bytes(wheel())
    assert main(["install", str(file)]) == 0
    assert (place / "pack_demo" / "__init__.py").is_file()
    assert "Installed pack-demo 0.1.0" in capsys.readouterr().out
    assert pack_install.installed_here("pack-demo", place)


def test_the_install_command_refuses_a_file_that_needs_compiling_and_a_missing_file(tmp_path, monkeypatch, capsys):
    from engine.cli import main

    monkeypatch.setattr(pack_install, "target", lambda: tmp_path)
    native = tmp_path / "native.whl"
    native.write_bytes(wheel(tag="cp312-cp312-macosx_11_0_arm64", purelib="false"))
    assert main(["install", str(native)]) == 1
    assert "pure Python" in capsys.readouterr().err
    assert main(["install", str(tmp_path / "nothing.whl")]) == 1
