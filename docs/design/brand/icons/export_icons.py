"""Export platform icons from already rendered SVG PNG sources."""

import argparse
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path

from PIL import Image


def resized(image: Image.Image, size: int) -> Image.Image:
    """Resize without upscaling, using premultiplied alpha to avoid dark edges."""
    if type(size) is not int or size < 1 or image.width != image.height or size > image.width:
        raise ValueError("Supply a square render at least as large as the requested positive size")
    return image.convert("RGBa").resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")


def one_color(image: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """Retain only a render's alpha mask and a chosen solid color."""
    result = Image.new("RGBA", image.size, (*color, 255))
    result.putalpha(image.convert("RGBA").getchannel("A"))
    return result


def ico_bytes(frames: Mapping[int, Image.Image]) -> bytes:
    """Keep explicitly supplied artwork for every ICO frame size."""
    if not frames or any(
        type(size) is not int or not 1 <= size <= 256 or image.size != (size, size) for size, image in frames.items()
    ):
        raise ValueError("ICO frames must match their requested square sizes, from 1 through 256")
    ordered = [frames[size].convert("RGBA") for size in sorted(frames, reverse=True)]
    output = BytesIO()
    ordered[0].save(output, format="ICO", sizes=[(size, size) for size in sorted(frames)], append_images=ordered[1:])
    return output.getvalue()


def export_icons(render_dir: Path, output_dir: Path) -> None:
    """Read explicit render files and write PNGs, platform icon sets, and ICOs."""
    sources = {}
    for name in ("app-1024", "clean-1024", "dark-1024", "small-256", "template-256", "favicon-256"):
        with Image.open(render_dir / f"{name}.png") as image:
            image.load()
            expected = 1024 if name.endswith("1024") else 256
            if image.format != "PNG" or image.size != (expected, expected):
                raise ValueError(f"Render {name} must be an {expected}-pixel square PNG")
            sources[name] = image.convert("RGBA")
    windows_sizes = (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 128, 256)
    png_sizes = sorted(set(windows_sizes) | {512, 1024})
    app_frames = {}
    for size in png_sizes:
        source = sources["small-256"] if size == 16 else sources["app-1024" if size >= 512 else "clean-1024"]
        app_frames[size] = resized(source, size)
    slots = (
        ("icon_16x16.png", 16, True),
        ("icon_16x16@2x.png", 32, True),
        ("icon_32x32.png", 32, False),
        ("icon_32x32@2x.png", 64, False),
        ("icon_128x128.png", 128, False),
        ("icon_128x128@2x.png", 256, False),
        ("icon_256x256.png", 256, False),
        ("icon_256x256@2x.png", 512, False),
        ("icon_512x512.png", 512, False),
        ("icon_512x512@2x.png", 1024, False),
    )
    for folder in ("png", "dark", "Thimbleby.iconset", "template-black", "template-white", "favicon"):
        (output_dir / folder).mkdir(parents=True, exist_ok=True)
    for size, image in app_frames.items():
        image.save(output_dir / "png" / f"app-{size}.png")
        if size > 16:
            resized(sources["dark-1024"], size).save(output_dir / "dark" / f"app-{size}.png")
    for name, size, small in slots:
        image = resized(sources["small-256"], size) if small else app_frames[size]
        image.save(output_dir / "Thimbleby.iconset" / name)
    (output_dir / "Thimbleby.ico").write_bytes(ico_bytes({size: app_frames[size] for size in windows_sizes}))
    tray_sizes = (16, 20, 24, 32, 40, 48, 64)
    for label, color in (("black", (0, 0, 0)), ("white", (255, 255, 255))):
        frames = {}
        for size in sorted(set(tray_sizes) | {18, 36}):
            image = one_color(resized(sources["template-256"], size), color)
            image.save(output_dir / f"template-{label}" / f"template-{size}.png")
            frames[size] = image
        (output_dir / f"tray-{label}.ico").write_bytes(ico_bytes({size: frames[size] for size in tray_sizes}))
        frames[18].save(output_dir / f"template-{label}" / "ThimblebyTemplate.png")
        frames[36].save(output_dir / f"template-{label}" / "ThimblebyTemplate@2x.png")
    favicons = {size: resized(sources["favicon-256"], size) for size in (16, 32, 48)}
    for size, image in favicons.items():
        image.save(output_dir / "favicon" / f"favicon-{size}.png")
    (output_dir / "favicon.ico").write_bytes(ico_bytes(favicons))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renders", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    export_icons(args.renders, args.out)


if __name__ == "__main__":
    main()
