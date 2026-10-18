from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import pytest
from export_icons import ico_bytes, one_color, resized
from PIL import Image


def test_resize_dimensions_and_input_unchanged():
    source = Image.new("RGBA", (64, 64), (116, 30, 37, 128))
    result = resized(source, 16)
    assert result.size == (16, 16)
    assert source.size == (64, 64)
    assert source.getpixel((0, 0)) == (116, 30, 37, 128)


@pytest.mark.parametrize("size", [0, -1, 65, True, 1.5])
def test_bad_resize(size):
    with pytest.raises(ValueError):
        resized(Image.new("RGBA", (64, 64)), size)


def test_nonsquare_source_rejected():
    with pytest.raises(ValueError):
        resized(Image.new("RGBA", (64, 32)), 16)


def test_one_color_preserves_alpha():
    source = Image.new("RGBA", (16, 16), (116, 30, 37, 100))
    result = one_color(source, (255, 255, 255))
    assert result.getpixel((8, 8)) == (255, 255, 255, 100)
    assert source.getpixel((8, 8)) == (116, 30, 37, 100)


def test_ico_preserves_each_custom_frame():
    frames = {
        16: Image.new("RGBA", (16, 16), (255, 0, 0, 255)),
        32: Image.new("RGBA", (32, 32), (0, 255, 0, 255)),
        256: Image.new("RGBA", (256, 256), (0, 0, 255, 255)),
    }
    with Image.open(BytesIO(ico_bytes(frames))) as icon:
        assert icon.ico.sizes() == {(16, 16), (32, 32), (256, 256)}
        assert icon.ico.getimage((16, 16)).getpixel((8, 8)) == (255, 0, 0, 255)
        assert icon.ico.getimage((32, 32)).getpixel((8, 8)) == (0, 255, 0, 255)


@pytest.mark.parametrize("frames", [{}, {512: Image.new("RGBA", (512, 512))}, {16: Image.new("RGBA", (32, 32))}])
def test_bad_ico_frames(frames):
    with pytest.raises(ValueError):
        ico_bytes(frames)


def test_vector_sources_are_editable_without_embedded_rasters():
    root = Path(__file__).parent / "svg"
    for path in root.glob("*.svg"):
        tree = ElementTree.fromstring(path.read_text())
        assert not any(element.tag.endswith("}image") for element in tree.iter())
        assert any(element.tag.endswith("}path") for element in tree.iter())


def test_texture_only_in_large_master():
    root = Path(__file__).parent / "svg"
    assert 'id="dimples"' in (root / "thimbleby-master.svg").read_text()
    assert 'id="dimples"' not in (root / "thimbleby-clean.svg").read_text()


def test_template_uses_transparent_cutout():
    path = Path(__file__).parent / "exports" / "template-black" / "template-16.png"
    with Image.open(path) as image:
        assert image.size == (16, 16)
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((5, 10))[3] < 50
        assert image.getpixel((8, 6))[3] > 240
        assert all(pixel[:3] == (0, 0, 0) for pixel in image.get_flattened_data() if pixel[3])


def test_delivered_app_ico_sizes():
    path = Path(__file__).parent / "exports" / "Thimbleby.ico"
    expected = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 128, 256)
    with Image.open(path) as image:
        assert image.ico.sizes() == {(size, size) for size in expected}


def test_delivered_favicon():
    path = Path(__file__).parent / "exports" / "favicon.ico"
    with Image.open(path) as image:
        assert image.ico.sizes() == {(16, 16), (32, 32), (48, 48)}


def test_iconset_slots():
    root = Path(__file__).parent / "exports" / "Thimbleby.iconset"
    assert len(list(root.glob("*.png"))) == 10
    for logical in (16, 32, 128, 256, 512):
        for suffix, scale in (("", 1), ("@2x", 2)):
            with Image.open(root / f"icon_{logical}x{logical}{suffix}.png") as image:
                assert image.size == (logical * scale, logical * scale)


def test_small_retina_slot_keeps_small_artwork():
    root = Path(__file__).parent / "exports" / "Thimbleby.iconset"
    with Image.open(root / "icon_16x16@2x.png") as small, Image.open(root / "icon_32x32.png") as regular:
        assert small.size == regular.size
        assert small.tobytes() != regular.tobytes()


def test_delivered_icns_has_all_ten_slots():
    path = Path(__file__).parent / "exports" / "Thimbleby.icns"
    with Image.open(path) as image:
        assert set(image.info["sizes"]) == {
            (logical, logical, scale) for logical in (16, 32, 128, 256, 512) for scale in (1, 2)
        }
        assert image.icns.getimage((16, 16, 1)).size == (16, 16)
