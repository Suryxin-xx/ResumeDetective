from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops


def content_box(image: Image.Image) -> tuple[int, int, int, int]:
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, background).convert("L")
    # Ignore the generator's very soft outer shadow so the mark fills small icons.
    mask = diff.point(lambda value: 255 if value > 24 else 0)
    box = mask.getbbox()
    if box is None:
        raise ValueError("icon source contains no visible content")
    return box


def square_crop(image: Image.Image) -> Image.Image:
    left, top, right, bottom = content_box(image)
    width, height = right - left, bottom - top
    padding = round(max(width, height) * 0.04)
    size = max(width, height) + padding * 2
    center_x = (left + right) // 2
    center_y = (top + bottom) // 2
    crop = (
        center_x - size // 2,
        center_y - size // 2,
        center_x + (size - size // 2),
        center_y + (size - size // 2),
    )
    background = image.convert("RGB").getpixel((0, 0))
    canvas = Image.new("RGB", (size, size), background)
    source_box = (
        max(0, crop[0]),
        max(0, crop[1]),
        min(image.width, crop[2]),
        min(image.height, crop[3]),
    )
    canvas.paste(
        image.crop(source_box).convert("RGB"),
        (source_box[0] - crop[0], source_box[1] - crop[1]),
    )
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare ResumeDetective PNG and ICO assets")
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source = Image.open(args.source)
    icon = square_crop(source).resize((1024, 1024), Image.Resampling.LANCZOS)
    icon.save(args.output_dir / "app-icon.png", optimize=True)
    icon.save(
        args.output_dir / "app-icon.ico",
        format="ICO",
        sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.resize((size, size), Image.Resampling.LANCZOS).save(args.output_dir / f"app-icon-{size}.png", optimize=True)


if __name__ == "__main__":
    main()
