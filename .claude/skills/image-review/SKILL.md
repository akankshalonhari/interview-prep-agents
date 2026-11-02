---
name: image-review
description: Review any image before it's committed to this public repo (screenshots, diagrams, photos, GIFs, SVGs in docs, notebooks or PRs), then fix what shouldn't be public. Use when a change or PR adds or updates images, when a reviewer asks to check screenshots, or when the user asks to redact, blur, pixelate or crop an image. Runs an OCR scan for names, usernames, computer names, home paths, emails, tokens and image metadata, reviews each image at full size for what OCR misses (faces, other repos, tabs, outdated content), reports findings in a table, and pixelates or crops with measured, verified edits before anything is committed.
---

# Image review

This repo is public (see `SECURITY.md`: "don't commit real people's ... personal data"). Images leak more than people expect, usually at the window edges. Treat the review like a test suite: scan automatically, then look at each image yourself, fix in small checked steps, and get the user's OK before committing.

## Tools

Both scripts need Pillow, which isn't a project dependency. Run them through uv so nothing gets installed:

```bash
uv run --with pillow python .claude/skills/image-review/scripts/scan_images.py --help
uv run --with pillow python .claude/skills/image-review/scripts/image_tool.py --help
```

- **`scan_images.py`** reads the text in each image with **OCR (Optical Character Recognition)** using `tesseract`, checks image metadata and file size, and prints a findings table with each finding's position. It exits 1 on high-severity findings, like a failing test. Matches are masked, because the output may be shared or logged publicly.
- **`image_tool.py`** has `preview` (convert or zoom), `measure` (exact text position), `pixelate` and `crop`.

The scan needs `tesseract`: `brew install tesseract` on macOS, `sudo apt install tesseract-ocr` on Ubuntu. Without it, run the scan with `--no-ocr`, which checks only metadata, size and SVGs, and rely on the visual review. If uv isn't available, use any Python that has Pillow. Write edited images to the scratchpad first, never straight over the originals.

## 1. Find and scan the images

```bash
uv run --with pillow python .claude/skills/image-review/scripts/scan_images.py --changed-since <base>
```

`<base>` is the PR's base, for example `upstream/main` for a PR from a fork. To scan specific files, pass the paths instead. If the images exist only on GitHub, extract them first with `git show <sha>:<path> > <scratchpad>/<name>`. Images pasted into a PR description or comment aren't in the repo, so ask the user for the file.

## 2. Look at each one at full size

OCR misses things. In testing it missed a username in one of three terminal prompts. So always check images visually too.

- Note each image's size in pixels and on disk.
- Open every image with the Read tool. Convert WebP and GIF to PNG first: `image_tool.py preview in.webp out.png`.
- A full-size view is scaled down, so zoom into the edges, any text, and every box the scan reported: `image_tool.py preview in.png out.png --box X0,Y0,X1,Y1 --scale 2`.

Check for:

| Look for | Typical places |
|---|---|
| Real names, account names, plan names, avatars, faces | App sidebars and footers, profile menus, photos |
| macOS/Linux username and computer name | Terminal prompts (`user@Host-MacBook-Air`), `rootdir:` lines, `/Users/<name>/...` paths |
| Emails, phone numbers | Git output, profile menus, form fields |
| Tokens, API keys, passwords, cookies | Terminals, `.env` files, URLs with `?token=` |
| Other repos, private org names, internal URLs | Browser tabs, address bar, file trees, recent projects |
| Notifications, messages, calendar items | Badges, toasts, menu bar |
| Security details | "no SSH keys on this Mac", hostnames, IPs |
| Metadata | GPS location, author or camera fields (the scan reports these) |
| **Outdated content** | Docs or code shown in the image that no longer match the current files |

GitHub usernames and fork URLs that already appear in the PR are public anyway. List them, but they don't need hiding.

## 3. Report before changing anything

Give the user one table, one row per image, saying what the scan and your own look found and what you'd do (pixelate, crop, replace, strip metadata, or leave it). Separate what's sensitive from what's merely outdated. Ask which fixes to make. Don't edit, commit or push without an answer.

## 4. Fix, measuring first

Pixelate personal details. Don't blur, because blurred text can sometimes be recovered. Start from the scan's box, then measure the exact text position:

```bash
image_tool.py measure in.png --rows 697,712 --from-x 800 --to-x 1400
image_tool.py pixelate in.png <scratchpad>/out.png --box 874,697,992,712 --box 864,868,1092,884
```

- One `--box` per secret. Make it a little wider than the text, but leave nearby context readable.
- For outdated or unneeded parts, **crop** to the part the doc describes: `image_tool.py crop in.png out.png --box X0,Y0,X1,Y1`.
- Pixelate first, then crop the pixelated file, so the coordinates stay the same.
- `image_tool.py` re-saves the image without its original metadata, which also removes GPS and author fields.
- Keep the original format: a `.webp` stays `.webp`, so links in the docs don't break.

## 5. Verify every edit

- Re-run `scan_images.py` on the edited files. It should pass.
- Zoom into each pixelated spot with `preview --box ... --scale 2` and confirm no letters are left, for example the first letter of a username or `/Users/<name>` in a path. Redo it with a corrected box if anything shows.
- Look at each cropped image whole, and check that what the doc says about it is still true.

## 6. Hand it back

- Show the user the edited images (send them, or open them) before they go into the repo.
- Once the user approves, copy them over the originals and update each image's alt text in the Markdown to match the crop.
- Report the size before and after.
- Commit with a message that says what was redacted or cropped and why. Push only when the user asks.
