"""Find, pixelate and crop parts of an image before it goes into the public repo.

Needs Pillow, which isn't a project dependency. Run it with uv so nothing is installed:

    uv run --with pillow python .claude/skills/image-review/scripts/image_tool.py <command> ...

Commands:

    preview IMAGE OUT.png [--box X0,Y0,X1,Y1] [--scale N]
        Save a PNG copy (WebP included) to look at, optionally only one region, enlarged N times.

    measure IMAGE --rows Y0,Y1 [--from-x X] [--to-x X] [--threshold 120] [--gap 5]
        Print the x ranges of dark text inside a horizontal band, so boxes can be placed exactly
        instead of guessed from a scaled-down view.

    pixelate IMAGE OUT --box X0,Y0,X1,Y1 [--box ...] [--block 10]
        Replace each box with large blocks. Pixelation is used instead of blur because blurred
        text can sometimes be recovered.

    crop IMAGE OUT --box X0,Y0,X1,Y1
        Keep only that region.

Coordinates are pixels in the original image: x to the right, y down, (0, 0) top-left.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def parse_box(text: str) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = (int(v) for v in text.split(","))
    if x1 <= x0 or y1 <= y0:
        raise argparse.ArgumentTypeError(f"box {text} must be X0,Y0,X1,Y1 with X1>X0 and Y1>Y0")
    return x0, y0, x1, y1


def save(im: Image.Image, out: str) -> None:
    kwargs = {"quality": 90, "method": 6} if out.lower().endswith(".webp") else {"optimize": True}
    im.save(out, **kwargs)
    print(f"saved {out} ({im.size[0]}x{im.size[1]}, {Path(out).stat().st_size // 1024} KB)")


def preview(args: argparse.Namespace) -> None:
    im = Image.open(args.image).convert("RGB")
    if args.box:
        im = im.crop(args.box)
    if args.scale != 1:
        im = im.resize((im.width * args.scale, im.height * args.scale), Image.NEAREST)
    save(im, args.out)


def measure(args: argparse.Namespace) -> None:
    im = Image.open(args.image).convert("L")
    y0, y1 = (int(v) for v in args.rows.split(","))
    to_x = args.to_x if args.to_x is not None else im.width
    xs = [
        x
        for x in range(args.from_x, to_x)
        if any(im.getpixel((x, y)) < args.threshold for y in range(y0, y1))
    ]
    if not xs:
        print("no dark pixels in that band; try another --threshold or check the rows")
        return
    runs, start, prev = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - prev > args.gap:
            runs.append((start, prev))
            start = x
        prev = x
    runs.append((start, prev))
    print(f"image {im.width}x{im.height}, rows {y0}-{y1}: text runs (x0, x1) =")
    for r in runs:
        print(f"  {r[0]}-{r[1]}")


def pixelate(args: argparse.Namespace) -> None:
    im = Image.open(args.image).convert("RGB")
    for box in args.box:
        region = im.crop(box)
        w, h = region.size
        small = region.resize((max(1, w // args.block), max(1, h // args.block)), Image.BILINEAR)
        im.paste(small.resize((w, h), Image.NEAREST), box)
    save(im, args.out)


def crop(args: argparse.Namespace) -> None:
    save(Image.open(args.image).convert("RGB").crop(args.box), args.out)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preview")
    p.add_argument("image")
    p.add_argument("out")
    p.add_argument("--box", type=parse_box)
    p.add_argument("--scale", type=int, default=1)
    p.set_defaults(func=preview)

    p = sub.add_parser("measure")
    p.add_argument("image")
    p.add_argument("--rows", required=True)
    p.add_argument("--from-x", type=int, default=0)
    p.add_argument("--to-x", type=int)
    p.add_argument("--threshold", type=int, default=120)
    p.add_argument("--gap", type=int, default=5)
    p.set_defaults(func=measure)

    p = sub.add_parser("pixelate")
    p.add_argument("image")
    p.add_argument("out")
    p.add_argument("--box", type=parse_box, action="append", required=True)
    p.add_argument("--block", type=int, default=10)
    p.set_defaults(func=pixelate)

    p = sub.add_parser("crop")
    p.add_argument("image")
    p.add_argument("out")
    p.add_argument("--box", type=parse_box, required=True)
    p.set_defaults(func=crop)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
