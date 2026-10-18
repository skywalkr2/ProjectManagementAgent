# Reginald’s bow — icon master

These editable SVGs redraw the latest `02-reginalds-bow-refined.png` concept board: a cream thimble, bold burgundy bow, brass rim, and deep burgundy rounded square. They are purpose-built vectors, not a raster embedded in an SVG or an exact automatic trace of the generated board.

## Artwork

- `svg/thimbleby-master.svg`: full-size editable master, including faint dimples. Use for 512 and 1024 physical pixels.
- `svg/thimbleby-clean.svg`: matching master with the texture layer removed. Use for 20–256 physical pixels.
- `svg/thimbleby-small.svg`: simplified 16-pixel burgundy silhouette with a transparent bow cutout. Also used for the 16-point Retina slot, rendered at 32 physical pixels.
- `svg/menu-template.svg`: black, single-color filled silhouette with transparent bow cutouts, drawn on a 16-unit grid. The holes are transparency, not white paint. There is no colored tile, texture, or tiny gold rim.
- `svg/thimbleby-dark.svg`: clean color variant with a fine brass edge to separate it from dark backgrounds.
- `svg/favicon.svg`: simplified cream-on-burgundy web icon without dimples or a thin rim. This separate optical variant stays recognizable at small sizes.

The principal colors are burgundy `#741E25`, cream `#FFF2D8`, and brass `#B59859`; the main tile and rim also have restrained gradients. Artwork uses paths and simple shapes, with no fonts or embedded images. The large master includes a clipped dimple pattern. Preview PNGs contain real exported small sizes, alongside one enlarged nearest-neighbor 16-pixel example.

## macOS iconset — all ten slots

The logical size appears in each filename; Retina doubles the actual pixel dimensions.

| Filename | PNG pixels |
| --- | --- |
| `icon_16x16.png` | 16 × 16 |
| `icon_16x16@2x.png` | 32 × 32 |
| `icon_32x32.png` | 32 × 32 |
| `icon_32x32@2x.png` | 64 × 64 |
| `icon_128x128.png` | 128 × 128 |
| `icon_128x128@2x.png` | 256 × 256 |
| `icon_256x256.png` | 256 × 256 |
| `icon_256x256@2x.png` | 512 × 512 |
| `icon_512x512.png` | 512 × 512 |
| `icon_512x512@2x.png` | 1024 × 1024 |

The two 32-pixel files intentionally differ: the 16-point Retina slot uses the simplified silhouette, while the 32-point regular slot uses the color tile. The delivered `exports/Thimbleby.icns` contains all ten resources, was parsed with Pillow, and was recognized as an ICNS file by the native image utility. The PNG iconset is also included. Standard conversion on macOS is:

```text
iconutil -c icns exports/Thimbleby.iconset -o exports/Thimbleby.icns
```

The native iconutil converter rejected the otherwise correctly sized iconset in this execution environment; the included ICNS was assembled from the ten PNG resources directly instead. The exporter below does not regenerate ICNS. The container and PNG slots were validated independently.

## Windows ICO sizes

The documented Win32 minimum is **16, 24, 32, 48, and 256** pixels. The delivered `Thimbleby.ico` additionally covers common scaling requests:

**16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 128, 256** pixels square.

There is no single mandatory exhaustive ICO size list for every Windows UI. This set covers the documented context-menu, taskbar, and Start scaling sizes, with 128 added as a useful intermediate. These are ICO frames, not the separate image requirements for a store-package manifest. No frame exceeds ICO's 256-pixel dimension limit.

The small app frame uses its own optical artwork. Explicit frame images are passed to Pillow so it does not silently replace that frame by shrinking the largest icon.

## Menu bar, tray, and favicon

Use the black `ThimblebyTemplate.png` and `ThimblebyTemplate@2x.png` at 18 and 36 physical pixels for an 18-point menu-bar image. Set the native image's template flag so macOS can tint it. A filename or SVG alone does not make every GUI toolkit treat an image as a template. The 16-pixel template PNG is supplied for smaller uses.

Windows does not apply the same native template convention. Choose the supplied black artwork on light backgrounds and white artwork on dark backgrounds. `tray-black.ico` and `tray-white.ico` each contain 16, 20, 24, 32, 40, 48, and 64-pixel frames. Theme selection belongs to the app. All template PNGs retain a single RGB color with antialiased alpha edges.

The favicon package contains `svg/favicon.svg`, `exports/favicon.ico` with 16/32/48 frames, and individual PNGs at those sizes. Use the SVG for scalable browser tabs and the ICO as a fallback.

## Exporting with Python

Pillow does not rasterize SVG. This deliberately small exporter accepts already rasterized PNGs, allowing SVG rendering to stay outside the Python dependency set. All required renders are included under `renders/`:

```text
app-1024.png        textured master, 1024 × 1024
clean-1024.png      clean master, 1024 × 1024
dark-1024.png       dark-background master, 1024 × 1024
small-256.png       small optical SVG rendered at 256 × 256
template-256.png    monochrome SVG rendered at 256 × 256
favicon-256.png     favicon SVG rendered at 256 × 256
```

After editing an SVG, rerender the corresponding PNG at the dimensions above with a reliable SVG renderer. For example, Inkscape supports commands of this form:

```text
inkscape svg/thimbleby-master.svg --export-type=png --export-width=1024 --export-height=1024 --export-filename=renders/app-1024.png
inkscape svg/thimbleby-clean.svg --export-type=png --export-width=1024 --export-height=1024 --export-filename=renders/clean-1024.png
inkscape svg/thimbleby-dark.svg --export-type=png --export-width=1024 --export-height=1024 --export-filename=renders/dark-1024.png
inkscape svg/thimbleby-small.svg --export-type=png --export-width=256 --export-height=256 --export-filename=renders/small-256.png
inkscape svg/menu-template.svg --export-type=png --export-width=256 --export-height=256 --export-filename=renders/template-256.png
inkscape svg/favicon.svg --export-type=png --export-width=256 --export-height=256 --export-filename=renders/favicon-256.png
```

The supplied renders were produced with a Skia-based SVG renderer. Some basic SVG converters do not correctly support gradients, clipped patterns, or fill rules; inspect the result before exporting the platform sizes.

With Python 3.12 and the pinned Pillow dependency installed, run:

```text
python export_icons.py --renders renders --out exports
```

The script writes PNGs, the complete iconset folder, the app ICO, both tray ICOs, and favicon ICO. It refuses undersized or nonsquare renders, preserves custom frames, and uses premultiplied-alpha resizing to avoid dark fringes. Pure image helpers are separated from the explicitly requested filesystem export operation. No clock or network access occurs.

Tests validate custom ICO frames, all ten iconset/ICNS slots, transparent bow cutouts, one-color pixels, editable SVGs, and invalid resize requests. Run `python -m pytest -q`, `ruff check .`, and `ruff format --check .`. Sources by name: Asset Catalog Format Reference — Icon Set Type; Construct your Windows app's icon; Pillow image-file-format documentation for ICO and ICNS; native template-image documentation.
