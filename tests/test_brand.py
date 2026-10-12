"""The brand color, logo, theme and density reach the screen through the runtime config (design 7.12)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.app import create_app
from engine.config.schema import BrandSettings
from engine.workspace import init_workspace
from tests.conftest import DEMO_B

TOKEN = "test-token-value"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def client_for(tmp_path, flags):
    ws = init_workspace(tmp_path / "ws", template=DEMO_B, git=False)
    (ws.config_dir / "mark.png").write_bytes(PNG)
    cfg = ws.config(env={}, flags={"server.base_path": "/", **flags})
    app = create_app(ws, cfg, TOKEN, ui_dist=tmp_path / "no-ui")
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})


def test_the_runtime_config_carries_the_appearance_settings(tmp_path):
    flags = {"ui.brand.color": "#225588", "ui.brand.logo": "mark.png", "ui.theme": "dark", "ui.density": "compact"}
    with client_for(tmp_path, flags) as client:
        rc = client.get("/api/runtime-config").json()
        assert (rc["brand_color"], rc["logo"], rc["theme"], rc["density"]) == ("#225588", True, "dark", "compact")
        logo = client.get("/api/brand/logo")
        assert logo.status_code == 200 and logo.content == PNG and logo.headers["content-type"] == "image/png"
        assert "default-src 'none'" in logo.headers["content-security-policy"]


def test_a_missing_logo_shows_the_monogram(tmp_path):
    with client_for(tmp_path, {"ui.brand.logo": "absent.svg"}) as client:
        assert client.get("/api/runtime-config").json()["logo"] is False
        assert client.get("/api/brand/logo").status_code == 404


@pytest.mark.parametrize("logo", ["../secret.png", "sub/mark.png", ".hidden.png", "mark.gif"])
def test_a_logo_is_an_image_file_in_the_config_folder_only(logo):
    with pytest.raises(ValidationError):
        BrandSettings(logo=logo)


def test_a_brand_color_is_a_hex_color():
    with pytest.raises(ValidationError):
        BrandSettings(color="indigo")
