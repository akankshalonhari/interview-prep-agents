---
name: screenshot-review
description: Review screenshots and other images before they're committed to this public repo, then fix what shouldn't be public. Use when a change adds or updates images (docs/, notebooks, PR assets), when a reviewer asks to check screenshots, or when the user asks to redact, blur, pixelate or crop an image. Checks each image at full size for names, usernames, computer names, home paths, emails, tokens, other repos, tabs and outdated content, reports findings in a table, and pixelates or crops with a measured, verified edit before anything is committed.
---

# Screenshot review

This repo is public (see `SECURITY.md`: "don't commit real people's ... personal data"). Screenshots leak more than people expect, usually at the window edges. Review every image deliberately, fix it in small checked steps, and get the user's OK before committing.

The helper script needs Pillow, which isn't a project dependency. Run it through uv so nothing gets installed:

```bash
uv run --with pillow python .claude/skills/screenshot-review/scripts/screenshot_tool.py --help
```

If uv isn't available, use any Python that has Pillow (`python3 -c "import PIL"`). Write edited images to the scratchpad first, never straight over the originals.

## 1. Find the images

List the images the change adds or modifies, for example against the PR's base:

```bash
git diff --name-only --diff-filter=AM <base>...HEAD | grep -iE '\.(png|jpe?g|gif|webp|svg)$'
```

For a PR from a fork, compare against `upstream/main`. If the images are only on GitHub, extract them with `git show <sha>:<path> > <scratchpad>/<name>`.

## 2. Look at each one at full size

- Note each image's size in pixels and on disk. The reviewer may ask about the total.
- Open every image with the Read tool. Convert WebP to PNG first: `screenshot_tool.py preview in.webp out.png`.
- A full-size view is scaled down, so zoom into the edges and anything that looks like text: `preview in.png out.png --box X0,Y0,X1,Y1 --scale 2`. Check all four edges, the sidebar, the status bar, terminal prompts and the address bar.

Check for:

| Look for | Typical places |
|---|---|
| Real names, account names, plan names | App sidebars and footers, avatars, "signed in as" |
| macOS/Linux username and computer name | Terminal prompts (`user@Host-MacBook-Air`), `rootdir:` lines, `/Users/<name>/...` paths |
| Emails, phone numbers | Git output, profile menus, form fields |
| Tokens, API keys, passwords, cookies | Terminals, `.env` files, URLs with `?token=` |
| Other repos, private org names, internal URLs | Browser tabs, address bar, file trees, recent projects |
| Notifications, messages, calendar items | Badges, toasts, menu bar |
| Security details | "no SSH keys on this Mac", hostnames, IPs |
| **Outdated content** | Docs or code shown in the image that no longer match the current files |

GitHub usernames and fork URLs that already appear in the PR are public anyway. List them, but they don't need hiding.

## 3. Report before changing anything

Give the user one table, one row per image, saying what's visible and what you'd do (pixelate, crop, replace, or leave it). Separate what's sensitive from what's merely outdated. Ask which fixes to make. Don't edit, commit or push without an answer.

## 4. Fix, measuring first

Pixelate personal details. Don't blur, because blurred text can sometimes be recovered. Coordinates read off a scaled-down view are often wrong, so measure the exact text position first:

```bash
screenshot_tool.py measure in.png --rows 697,712 --from-x 800 --to-x 1400
screenshot_tool.py pixelate in.png <scratchpad>/out.png --box 874,697,992,712 --box 864,868,1092,884
```

- One `--box` per secret. Make it a little wider than the text, but leave nearby context readable.
- For outdated or unneeded parts, **crop** to the part the doc describes: `screenshot_tool.py crop in.png out.png --box X0,Y0,X1,Y1`.
- Pixelate first, then crop the pixelated file, so the coordinates stay the same.
- Keep the original format: a `.webp` stays `.webp`, so links in the docs don't break.

## 5. Verify every edit

- Zoom into each pixelated spot with `preview --box ... --scale 2` and confirm no letters are left, for example the first letter of a username or `/Users/<name>` in a path. Redo it with a corrected box if anything shows.
- Look at each cropped image whole, and check that what the doc says about it is still true.

## 6. Hand it back

- Show the user the edited images (send them, or open them) before they go into the repo.
- Once the user approves, copy them over the originals and update each image's alt text in the Markdown to match the crop.
- Report the size before and after.
- Commit with a message that says what was redacted or cropped and why. Push only when the user asks.
