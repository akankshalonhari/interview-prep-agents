"""Scan images for personal data and secrets before they reach the public repo.

Reads the text in each image with OCR (tesseract), checks image metadata and file size, and fails like
a test when it finds something. Used by the image-review skill.

    uv run --with pillow python .claude/skills/image-review/scripts/scan_images.py docs/images/*.png
    uv run --with pillow python .claude/skills/image-review/scripts/scan_images.py --changed-since upstream/main

Needs Pillow and the tesseract command (macOS: brew install tesseract, Ubuntu: apt install tesseract-ocr).
SVG files are text, so they're checked directly without OCR.

Findings never print the full matched text, since output may be logged publicly: they show the first two characters
and the position, which is enough to find and pixelate it.

Exit code: 0 when nothing at or above --fail-on was found, 1 when something was, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
SVG_EXTENSIONS = {".svg"}
SEVERITIES = ["low", "medium", "high"]

# (name, severity, pattern). Patterns run on one line of OCR text at a time.
RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("private key", "high", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", "high", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("API key", "high", re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}")),
    ("AWS access key", "high", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", "high", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("home folder path", "high", re.compile(r"(?:/Users/(?!Shared\b)|/home/|[A-Za-z]:\\Users\\)[\w.-]+")),
    ("email address", "high", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")),
    # user@host as in a shell prompt: the host has no dot, which tells it apart from an email. Both parts
    # need a few characters so OCR noise (window buttons read as "oe@eo") isn't reported.
    (
        "terminal user@host",
        "high",
        re.compile(r"(?<![\w.@-])[A-Za-z_][\w.-]+@[A-Za-z0-9][A-Za-z0-9-]{2,}(?![\w.@-])"),
    ),
    ("IP address", "medium", re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")),
]

# Matches that are fine to show: bot and placeholder addresses, loopback IPs.
ALLOWED = re.compile(
    r"noreply@|no-reply@|@users\.noreply\.github\.com|@example\.(?:com|org)|^git@github\.com$"
    r"|^(?:127\.0\.0\.1|0\.0\.0\.0|255\.255\.255\.\d+)$",
    re.IGNORECASE,
)

# EXIF tag ids: GPSInfo, Artist, Copyright, Make, Model, XPAuthor.
EXIF_TAGS = {
    34853: ("GPS location", "high"),
    315: ("author", "medium"),
    33432: ("copyright", "low"),
    271: ("camera make", "low"),
    272: ("camera model", "low"),
    40093: ("author", "medium"),
}
PNG_TEXT_KEYS = {"author": "medium", "comment": "low", "copyright": "low", "description": "low"}


@dataclass
class Finding:
    image: str
    severity: str
    rule: str
    sample: str  # masked
    box: tuple[int, int, int, int] | None = None

    @property
    def where(self) -> str:
        return ",".join(str(v) for v in self.box) if self.box else "-"


def mask(text: str) -> str:
    """Show only enough to recognise and locate a match, never the whole value."""
    return text[:2] + "*" * min(max(len(text) - 2, 3), 12)


def scan_text(line: str) -> list[tuple[str, str, str]]:
    """Return (rule, severity, masked sample) for each match in one line of text."""
    hits: list[tuple[str, str, str]] = []
    taken: list[tuple[int, int]] = []
    for name, severity, pattern in RULES:
        for m in pattern.finditer(line):
            if ALLOWED.search(m.group()) or any(s <= m.start() < e for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            hits.append((name, severity, mask(m.group())))
    return hits


def ocr_lines(path: Path, tesseract: str) -> list[tuple[str, tuple[int, int, int, int]]]:
    """OCR an image and return (line text, box in original pixels) for each line."""
    from PIL import Image, ImageSequence

    scale = 2  # small UI text reads much better enlarged
    with Image.open(path) as im:
        frame = next(ImageSequence.Iterator(im)).convert("L")
        big = frame.resize((frame.width * scale, frame.height * scale))
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "page.png"
        big.save(png)
        tsv = subprocess.run(
            [tesseract, str(png), "stdout", "tsv"], capture_output=True, text=True, check=True
        )

    lines: dict[tuple[str, str, str], list[tuple[str, int, int, int, int]]] = {}
    for row in tsv.stdout.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or not cols[11].strip():
            continue
        left, top, width, height = (int(v) for v in cols[6:10])
        lines.setdefault((cols[2], cols[3], cols[4]), []).append((cols[11], left, top, width, height))

    result = []
    for words in lines.values():
        text = " ".join(w[0] for w in words)
        x0 = min(w[1] for w in words) // scale
        y0 = min(w[2] for w in words) // scale
        x1 = max(w[1] + w[3] for w in words) // scale
        y1 = max(w[2] + w[4] for w in words) // scale
        result.append((text, (x0, y0, x1, y1)))
    return result


def metadata_findings(path: Path) -> list[Finding]:
    from PIL import Image

    found = []
    with Image.open(path) as im:
        exif = im.getexif()
        for tag, (rule, severity) in EXIF_TAGS.items():
            if exif.get(tag):
                found.append(Finding(str(path), severity, f"metadata: {rule}", mask(str(exif.get(tag)))))
        for key, value in (im.info or {}).items():
            severity = PNG_TEXT_KEYS.get(str(key).lower())
            if severity and isinstance(value, str) and value.strip():
                found.append(Finding(str(path), severity, f"metadata: {key}", mask(value)))
    return found


def scan_image(path: Path, tesseract: str | None, max_kb: int) -> list[Finding]:
    found: list[Finding] = []
    size_kb = path.stat().st_size // 1024
    if size_kb > max_kb:
        found.append(Finding(str(path), "low", f"large file ({size_kb} KB > {max_kb} KB)", "-"))

    if path.suffix.lower() in SVG_EXTENSIONS:
        for line in path.read_text(errors="replace").splitlines():
            found += [Finding(str(path), sev, rule, sample) for rule, sev, sample in scan_text(line)]
        return found

    found += metadata_findings(path)
    if tesseract:
        for text, box in ocr_lines(path, tesseract):
            found += [Finding(str(path), sev, rule, sample, box) for rule, sev, sample in scan_text(text)]
    return found


def changed_images(base: str) -> list[Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    exts = IMAGE_EXTENSIONS | SVG_EXTENSIONS
    return [Path(p) for p in out.splitlines() if Path(p).suffix.lower() in exts and Path(p).exists()]


def report(findings: list[Finding], scanned: list[Path], ocr: bool) -> str:
    lines = [
        f"Scanned {len(scanned)} image(s){'' if ocr else ' without OCR'}: {len(findings)} finding(s).",
        "",
    ]
    if findings:
        lines += ["| Image | Severity | What | Sample | Box (x0,y0,x1,y1) |", "|---|---|---|---|---|"]
        order = sorted(findings, key=lambda f: (f.image, -SEVERITIES.index(f.severity)))
        lines += [f"| `{f.image}` | {f.severity} | {f.rule} | `{f.sample}` | {f.where} |" for f in order]
        next_steps = (
            "Pixelate or crop each finding (see .claude/skills/image-review/SKILL.md), "
            "or confirm it's safe to publish. OCR can miss text, so also look at each image yourself."
        )
        lines += ["", next_steps]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("paths", nargs="*", type=Path, help="images to scan")
    parser.add_argument("--changed-since", metavar="BASE", help="scan images added or changed since BASE")
    parser.add_argument("--fail-on", choices=SEVERITIES + ["never"], default="high")
    parser.add_argument("--max-kb", type=int, default=500, help="flag files larger than this")
    parser.add_argument("--no-ocr", action="store_true", help="skip OCR (metadata, size and SVG only)")
    parser.add_argument("--tesseract", default="tesseract", help="path to the tesseract command")
    parser.add_argument(
        "--summary-file", type=Path, help="also append the report here (e.g. $GITHUB_STEP_SUMMARY)"
    )
    args = parser.parse_args(argv)

    paths = list(args.paths)
    if args.changed_since:
        paths += changed_images(args.changed_since)
    if not paths:
        print("No images to scan.")
        return 0

    tesseract = None if args.no_ocr else shutil.which(args.tesseract)
    if not args.no_ocr and not tesseract:
        print(f"'{args.tesseract}' not found. Install tesseract, or pass --no-ocr.", file=sys.stderr)
        return 2

    findings = [f for p in paths for f in scan_image(p, tesseract, args.max_kb)]
    text = report(findings, paths, ocr=tesseract is not None)
    print(text)
    if args.summary_file:
        with args.summary_file.open("a") as fh:
            fh.write("## Image review\n\n" + text + "\n")

    if args.fail_on == "never":
        return 0
    threshold = SEVERITIES.index(args.fail_on)
    return 1 if any(SEVERITIES.index(f.severity) >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
