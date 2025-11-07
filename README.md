# exported_splitter

A small, dependency-free Python utility that lives in the root of an **already-extracted** Garry's Mod addon and exports **one mini-addon per model**. Drop `exported_splitter.py` next to your `models/` and/or `materials/` folders, run it, pick model indices, and it will create `EXPORTED1`, `EXPORTED2`, … containing only the files required for each prop: the `.mdl` and its sidecars, the referenced `.vmt` material files (including nested `include`s) and any `.vtf` textures referenced by those VMTs.

No GMAs required. Pure stdlib. Works on Python **3.9+**.

---

## Features

- Scans the addon folder for `.mdl` files (prefers `models/` paths).
- For each chosen model:
  - Copies the `.mdl` and known sidecars (`.vvd`, `.vtx*`, `.ani`, `.phy`, etc.).
  - Greedily scans MDL bytes to find material candidates.
  - Parses VMT files for texture keys and `include` chains to gather `.vtf` dependencies.
  - Writes `split_manifest.json` with what was copied and any missing references.
  - Writes a simple `addon.json` so the export can be used directly as a plug-and-play mini-addon.
- Command-line or interactive selection; selection supports `all`, numeric lists, and ranges (`1,4-6,8`).
- No external libraries, no network, cross-platform (Windows/Linux/macOS).

---

## Quick start

1. Ensure Python 3.9+ is installed.
2. Extract the GMod addon you want to split (so you have `models/`, `materials/`, etc. as regular folders).
3. Put `exported_splitter.py` in the addon root (same level as `models/`).
4. Run:

```bash
python exported_splitter.py
```

or, to point at a different folder:

```bash
python exported_splitter.py /path/to/extracted_addon_folder
```

Follow the prompts to pick indices (for example `1,5-7,12` or `all`). The script will create `EXPORTED1`, `EXPORTED2`, ... in the same root folder.

---

## Selection syntax

- `all` or `*` — export every model found.
- `1,4,7` — export models 1, 4 and 7 (numbers shown in the interactive list).
- `3-6` — export models 3, 4, 5, 6.
- Combined tokens are allowed: `1,3-5,9`.

Indices are **1-based** and unique in the order specified.

---

## What gets created for each export

Inside each `EXPORTED#` directory:

- The model files: `.mdl` plus recognized sidecars (`.vvd`, `.vtx`, `.dx90.vtx`, `.ani`, `.phy`, etc.) when present.
- `materials/...` VMT files referenced (including files brought in via `include` statements).
- `.vtf` textures referenced from the VMTs (based on a conservative set of common VMT texture keys).
- `split_manifest.json` — a manifest listing copied files and any missing references (useful for troubleshooting).
- `addon.json` — a tiny addon manifest (type `model`) so the folder can be used directly as a mini-addon.

---

## Heuristics & behavior notes (limitations you should know)

- **MDL scanning is heuristic.** The script does a conservative, greedy string scan of the MDL binary to find likely material tokens. This works for common cases but may miss some references embedded in unusual formats.
- **VMT parsing is tolerant but simple.** It strips `//` comments and parses common key/value patterns. Extremely unusual VMT syntaxes might not be parsed perfectly.
- **Texture key list.** The script uses a predefined (case-insensitive) set of common VMT texture keys (`basetexture`, `bumpmap`, `detail`, `albedo`, etc.). If a material uses non-standard keys, the texture may not be discovered.
- **Case-insensitive matching.** The script builds a case-insensitive file index (`lc_map`) to handle filesystem case differences and typical addon path casing issues.
- **Missing files.** If referenced materials or textures are missing from the extracted folder, they will be listed in `split_manifest.json` and a warning will be printed to stderr.
- **No recomposition of materials.** The script does not alter VMTs; it copies them as-is. If your exported mini-addon expects different relative paths, you may need to edit VMTs manually afterward.
- **No compression / GMA creation.** If you need a `.gma`, use your preferred GMod packing workflow after export.

---

## Troubleshooting

- **No `.mdl` files found** — Ensure you run the script in the extracted addon root (the folder that actually contains `models/`), or pass that folder as an argument.
- **Warnings about missing VMT/VTF** — Check `EXPORTED#/split_manifest.json` to see which files were referenced but not found. You may need to locate them elsewhere (common assets are sometimes shared between addons).
- **Exported addon not showing in-game** — Ensure `addon.json` is present (the script writes one). Confirm the folder is at the correct location for GMod to load, or pack as a `.gma` using your normal tools.
- **Windows path oddities** — The script normalizes paths to POSIX-style internally; this is normal. If the script fails to find files on a Windows system, double-check for stray leading/trailing whitespace in filenames or very unusual encodings.

---

## Customization & tips

- `PAGE_SIZE` near the top controls how many models the script lists before pausing for `-- more --`. Change if you want longer/shorter pages.
- Add or remove members in `MODEL_SIDE_EXTS` to adjust which sidecar extensions are considered.
- You can run the script repeatedly — the exported directory names use `EXPORTED#` and the script picks the next available number automatically, avoiding collisions.
- If you need a more compact or indexed output (or if you expect thousands of models), consider adapting the script to write a CSV/DB of manifests or to batch exports programmatically.

---

## Security & etiquette

- Only run this script on your **own** extracted addons or with explicit permission from the addon author.
- Respect licenses of assets — copying and redistributing community-made models/textures without permission may violate the asset license or server rules.
- This tool is intended to help manage/trim addons for personal servers or testing. It is not a tool for redistribution without proper rights.

---

## Requirements

- Python 3.9 or newer.
- No external Python packages required.

---

## Example session

```text
$ python exported_splitter.py
Addon root: /home/me/addons/my_addon
Props found:
    1  props/vehicles/car.mdl
    2  models/props_furniture/chair.mdl
    3  models/props_debris/box.mdl

Total: 3

Enter indices (e.g. 1,5-7,12) or 'all': 1,3

Exporting 2 props...
  -> EXPORTED1: props/vehicles/car.mdl
  -> EXPORTED2: models/props_debris/box.mdl

=== Done ===
Created: 2 folder(s):
  EXPORTED1
  EXPORTED2
```

---

## Contributing

This script is intentionally small and dependency-free. If you want to improve detection heuristics, VMT parsing robustness, or add features (e.g., optional VTF resizing, automatic `.gma` packing, UI), feel free to fork and open a pull request.

---


## Contact / changelog

- v1.0 — initial utility: model-sidecars, MDL greedy scan, VMT include follow, VTF collection, `split_manifest.json`, `addon.json`.
- For questions or feature requests, [join the discord here](https://discord.com/invite/XsFxP88g)

---

Happy splitting — may your servers only load what they need!
