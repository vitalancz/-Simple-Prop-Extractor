#!/usr/bin/env python3
"""
exported_splitter.py

Drop this script in the **root of your already-extracted GMod addon** (same level as `models/` and/or `materials/`).
Run it, pick model indices, and it will export **one mini-addon per model** into EXPORTED1, EXPORTED2, ...
Each export contains only what's needed for that prop: .mdl + sidecars (.vvd, .vtx*, .ani, .phy), and all referenced
materials (.vmt) and textures (.vtf) discovered via VMT includes and common keys.

No GMAs involved. Pure stdlib. Python 3.9+.
"""

from __future__ import annotations
import os
import re
import sys
import json
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# -------------------- Config / Heuristics --------------------

MODEL_SIDE_EXTS = [
    ".mdl",
    ".vvd",
    ".phy",
    ".ani",
    ".vtx",
    ".dx80.vtx",
    ".dx90.vtx",
    ".sw.vtx",
]

# Common VMT texture keys (case-insensitive)
VMT_TEXTURE_KEYS = {
    "basetexture",
    "basetexture2",
    "bumpmap",
    "normalmap",
    "phongalbedotint",
    "phongexponenttexture",
    "selfillumtint",
    "lightwarptexture",
    "detail",
    "envmapmask",
    "ambientoccltexture",
    "blendmodulatetexture",
    "albedo",
    "heightmap",
    "mraotexture",
    "roughnesstexture",
    "metalictexture",
}

# Follow "include" to copy nested VMTs
VMT_INCLUDE_KEYS = {"include"}

PAGE_SIZE = 80  # just for nicer printing


# -------------------- Utils --------------------

def log(msg: str) -> None:
    print(msg, file=sys.stderr)

def to_posix(p: Path) -> str:
    return str(p.as_posix())

def build_file_index(root: Path) -> Tuple[List[str], Dict[str, str]]:
    """Return (all_files, lc_map) of relpaths under root (POSIX style)."""
    all_files: List[str] = []
    lc_map: Dict[str, str] = {}
    for fp in root.rglob("*"):
        if fp.is_file():
            rel = to_posix(fp.relative_to(root))
            all_files.append(rel)
            lc_map[rel.lower()] = rel
    return all_files, lc_map

def list_model_paths(all_files: List[str]) -> List[str]:
    """All .mdl relpaths, models/ first then others, alphabetically."""
    mdls = [p for p in all_files if p.lower().endswith(".mdl")]
    mdls.sort(key=lambda s: (0 if s.lower().startswith("models/") else 1, s.lower()))
    return mdls

def siblings_with_same_stem(rel_mdl: str) -> List[str]:
    """Return .mdl and known sidecar filenames sharing the same stem."""
    stem = rel_mdl[:-4] if rel_mdl.lower().endswith(".mdl") else rel_mdl
    return [rel_mdl] + [stem + ext for ext in MODEL_SIDE_EXTS]

def ensure_copy(root: Path, rel_path: str, out_root: Path, lc_map: Dict[str, str], copied: Set[str]) -> Optional[str]:
    """Copy rel_path (case-insensitive) into out_root, preserving subdirs. Track in `copied`."""
    key = rel_path.replace("\\", "/").lower()
    real_rel = lc_map.get(key)
    if not real_rel:
        return None
    if real_rel in copied:
        return real_rel
    src = root / real_rel
    dst = out_root / real_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    copied.add(real_rel)
    return real_rel

# -------------------- VMT/VTF discovery --------------------

def _parse_vmt_pairs(text: str) -> List[Tuple[str, str]]:
    # Strip line comments
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    pairs: List[Tuple[str, str]] = []
    pairs += re.findall(r'"\$?([a-z0-9_]+)"\s*"([^"]+)"', text, flags=re.IGNORECASE)
    pairs += re.findall(r"\$([a-z0-9_]+)\s+([^\s\"}]+)", text, flags=re.IGNORECASE)
    return pairs

def _norm_to_materials(p: str, ext: str) -> str:
    p = p.replace("\\", "/").strip().lower()
    if not p.endswith(ext):
        p = p + ext
    if not p.startswith("materials/"):
        p = "materials/" + p
    return p

def parse_vmt_for_dependencies(vmt_text: str) -> Tuple[Set[str], Set[str]]:
    """Return (vtf_paths, include_vmts) as relpaths under materials/."""
    vtfs: Set[str] = set()
    includes: Set[str] = set()
    for k, v in _parse_vmt_pairs(vmt_text):
        lk = k.lower()
        if lk in VMT_TEXTURE_KEYS:
            vtfs.add(_norm_to_materials(v, ".vtf"))
        elif lk in VMT_INCLUDE_KEYS:
            includes.add(_norm_to_materials(v, ".vmt"))
    return vtfs, includes

def scan_mdl_for_material_candidates(mdl_bytes: bytes) -> Set[str]:
    """Greedy scan of strings in an MDL to guess VMT paths."""
    mats: Set[str] = set()
    for m in re.finditer(rb"([A-Za-z0-9_\-\/\\\.]{4,})", mdl_bytes):
        token = m.group(1).decode(errors="ignore").replace("\\", "/")
        if "/" not in token:
            continue
        t = token.lower()
        if t.endswith(".vmt"):
            mats.add(t if t.startswith("materials/") else "materials/" + t)
        else:
            if "models/" in t or "materials/" in t:
                tt = t[len("materials/") :] if t.startswith("materials/") else t
                mats.add("materials/" + tt + ".vmt")
    return mats

def collect_vmt_and_vtf(root: Path, start_vmts: Iterable[str], lc_map: Dict[str, str]) -> Tuple[Set[str], Set[str]]:
    """Follow include-chains and gather all VTFs reachable from the starting VMT set."""
    to_visit = list(set(s.lower() for s in start_vmts))
    seen_vmts: Set[str] = set()
    vtfs: Set[str] = set()

    while to_visit:
        vmt_rel = to_visit.pop()
        if vmt_rel in seen_vmts:
            continue
        seen_vmts.add(vmt_rel)

        real_rel = lc_map.get(vmt_rel)
        if not real_rel:
            collapsed = vmt_rel.replace("materials/materials/", "materials/")
            real_rel = lc_map.get(collapsed)
        if not real_rel:
            log(f"[warn] VMT missing: {vmt_rel}")
            continue

        try:
            text = (root / real_rel).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            log(f"[warn] Failed reading VMT: {real_rel}")
            continue

        vtfs_in_this, includes = parse_vmt_for_dependencies(text)
        vtfs.update(v.lower() for v in vtfs_in_this)
        for inc in includes:
            if inc not in seen_vmts:
                to_visit.append(inc)
    return seen_vmts, vtfs

# -------------------- Dependency gather for a model --------------------

def gather_deps_for_model(root: Path, rel_mdl: str, all_files: List[str], lc_map: Dict[str, str]) -> Tuple[Set[str], Set[str], Set[str]]:
    """Return (model_files, vmt_files, vtf_files) that actually exist."""
    model_files: Set[str] = set()
    vmt_candidates: Set[str] = set()

    # model sidecars
    for candidate in siblings_with_same_stem(rel_mdl):
        key = candidate.replace("\\", "/").lower()
        if key in lc_map:
            model_files.add(lc_map[key])

    # scrape MDL for materials
    try:
        mdl_bytes = (root / lc_map[rel_mdl.lower()]).read_bytes()
        vmt_candidates |= scan_mdl_for_material_candidates(mdl_bytes)
    except Exception:
        log(f"[warn] Could not scan MDL bytes: {rel_mdl}")

    # heuristic: same tree + same basename
    mdl_path = Path(rel_mdl)
    if mdl_path.parent.parts:
        folder_hint = "/".join(mdl_path.parent.parts).lower()
        base_hint = mdl_path.stem.lower()
        vmt_candidates.add(f"materials/{folder_hint}/{base_hint}.vmt")
        for f in all_files:
            fl = f.lower()
            if fl.endswith(".vmt") and (base_hint in Path(fl).stem) and folder_hint in fl:
                vmt_candidates.add(fl)

    # only those that exist
    existing_vmts = {lc_map[v.lower()] for v in vmt_candidates if v.lower() in lc_map}
    all_vmts, all_vtfs = collect_vmt_and_vtf(root, existing_vmts, lc_map)
    return model_files, all_vmts, all_vtfs

# -------------------- Export naming --------------------

def next_export_number(root: Path) -> int:
    """Find next EXPORTED# number (1-based), skipping ones that already exist."""
    max_n = 0
    for p in root.iterdir():
        if p.is_dir():
            m = re.fullmatch(r"EXPORTED\s*(\d+)", p.name, flags=re.IGNORECASE)
            if m:
                try:
                    n = int(m.group(1))
                    max_n = max(max_n, n)
                except ValueError:
                    pass
    return max_n + 1

def export_name(n: int) -> str:
    # Use EXPORTED1, EXPORTED2, ... (no space) — simple and Windows-friendly
    return f"EXPORTED{n}"

# -------------------- Minimal UI --------------------

def print_models(models: List[str]) -> None:
    print("\nProps found:")
    if not models:
        print("  (none)")
        return
    for i, rel in enumerate(models, start=1):
        disp = rel[7:] if rel.lower().startswith("models/") else rel
        print(f"{i:5d}  {disp}")
        if i % PAGE_SIZE == 0:
            input("  -- more -- press Enter -- ")
    print(f"\nTotal: {len(models)}")

def parse_selection(spec: str, max_index: int) -> List[int]:
    """
    Parse "1,5-7,12" or "all". Returns 1-based unique indices in the **order given**.
    """
    spec = spec.strip().lower()
    if spec in {"all", "*"}:
        return list(range(1, max_index + 1))

    ordered: List[int] = []
    seen: Set[int] = set()
    tokens = [t.strip() for t in re.split(r"[,\s]+", spec) if t.strip()]
    for t in tokens:
        if "-" in t:
            a, b = t.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise ValueError(f"Bad range token: {t}")
            start, end = int(a), int(b)
            if start > end:
                start, end = end, start
            for i in range(start, end + 1):
                if 1 <= i <= max_index and i not in seen:
                    seen.add(i)
                    ordered.append(i)
        else:
            if not t.isdigit():
                raise ValueError(f"Bad index token: {t}")
            i = int(t)
            if 1 <= i <= max_index and i not in seen:
                seen.add(i)
                ordered.append(i)
    return ordered

# -------------------- Addon writer --------------------

def write_addon_json(out_dir: Path, title: str) -> None:
    addon = {
        "title": title,
        "type": "model",
        "tags": ["model", "prop"],
        "ignore": [".psd", ".db", ".blend1", ".md"],
    }
    (out_dir / "addon.json").write_text(json.dumps(addon, indent=2), encoding="utf-8")

def export_one(root: Path, rel_mdl: str, all_files: List[str], lc_map: Dict[str, str], export_dir: Path) -> List[str]:
    """Copy all needed files for one model into export_dir. Returns missing relpaths."""
    copied: Set[str] = set()
    missing: List[str] = []

    model_files, vmts, vtfs = gather_deps_for_model(root, rel_mdl, all_files, lc_map)

    for f in sorted(model_files):
        if ensure_copy(root, f, export_dir, lc_map, copied) is None:
            missing.append(f)
    for f in sorted(vmts):
        if ensure_copy(root, f, export_dir, lc_map, copied) is None:
            missing.append(f)
    for f in sorted(vtfs):
        if ensure_copy(root, f, export_dir, lc_map, copied) is None:
            missing.append(f)

    # small manifest for troubleshooting
    (export_dir / "split_manifest.json").write_text(
        json.dumps({"model": rel_mdl, "copied_files": sorted(copied), "missing": sorted(set(missing))}, indent=2),
        encoding="utf-8",
    )
    # addon.json for plug-and-play
    write_addon_json(export_dir, f"{Path(rel_mdl).stem} (exported)")
    return missing

# -------------------- Main --------------------

def main() -> int:
    # Default to the script's directory so you can just double-click/run in place
    try:
        script_dir = Path(__file__).resolve().parent
    except Exception:
        script_dir = Path.cwd()

    root = script_dir

    # allow optional arg: a different pack folder
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).expanduser()

    if not root.is_dir() or (not (root / "models").exists() and not (root / "materials").exists()):
        print("[!] Put this script in your extracted addon root (where `models/` lives),")
        print("    or pass the folder path as an argument.")
        print(f"    Current: {root}")
        return 1

    print(f"Addon root: {root}")

    all_files, lc_map = build_file_index(root)
    models = list_model_paths(all_files)

    if not models:
        print("[!] No .mdl files found. Are you in the right folder?")
        return 1

    print_models(models)

    # selection prompt
    while True:
        try:
            spec = input("\nEnter indices (e.g. 1,5-7,12) or 'all': ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 130
        if not spec:
            continue
        try:
            picks = parse_selection(spec, len(models))
        except ValueError as e:
            print(f"[!] {e}")
            continue
        if not picks:
            print("[!] Nothing selected.")
            continue
        break

    # Find starting export number (skip existing EXPORTED# folders)
    start_n = next_export_number(root)
    n = start_n

    print(f"\nExporting {len(picks)} props...")
    created_dirs: List[Path] = []
    failures = 0

    for idx_in_list in picks:
        rel_mdl = models[idx_in_list - 1]
        out_name = export_name(n)
        export_dir = root / out_name
        n += 1

        try:
            export_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            # If somehow it exists, bump until free
            while export_dir.exists():
                out_name = export_name(n)
                export_dir = root / out_name
                n += 1
            export_dir.mkdir(parents=True, exist_ok=True)

        disp = rel_mdl[7:] if rel_mdl.lower().startswith("models/") else rel_mdl
        print(f"  -> {out_name}: {disp}")
        try:
            missing = export_one(root, rel_mdl, all_files, lc_map, export_dir)
            if missing:
                log(f"     [warn] Missing {len(missing)} referenced file(s). See {export_dir/'split_manifest.json'}.")
            created_dirs.append(export_dir)
        except Exception as e:
            failures += 1
            log(f"     [ERROR] {e}")

    print("\n=== Done ===")
    print(f"Created: {len(created_dirs)} folder(s):")
    for p in created_dirs:
        print(f"  {p.name}")
    if failures:
        print(f"Failures: {failures} (see stderr for details)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
