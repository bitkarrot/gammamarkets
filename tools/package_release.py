#!/usr/bin/env python3
"""Build the LNbits remote-install release artifacts for infinitemarkets.

Outputs into ``dist/``:

- ``infinitemarkets-<version>.zip`` — single top-level directory
  ``infinitemarkets/`` containing the extension package, which is the layout
  LNbits' ``extract_archive`` expects (it copies the first top-level dir and
  reads ``config.json`` at its root). Only git-tracked files are packaged, so
  ``__pycache__`` and untracked assets never leak into the release.
- ``manifest.json`` — an LNbits extension-registry manifest whose
  ``extensions[]`` entry is an ExplicitRelease pointing at the zip release
  asset with its real sha256. Operators add this manifest's URL to
  ``lnbits_extensions_manifests`` (or install the zip directly).

The zip is deterministic: fixed entry order (``git ls-files`` order) and a
fixed mtime, so rebuilds of the same tree produce the same sha256.
"""

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT_DIR = "infinitemarkets"
REPO = "https://github.com/bitkarrot/infinitemarkets"
# ZipInfo refuses dates before 1980; a fixed timestamp keeps builds reproducible.
FIXED_DATE = (2025, 1, 1, 0, 0, 0)


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", EXT_DIR],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    files = [ln for ln in out.stdout.splitlines() if ln.strip()]
    if not files:
        sys.exit("error: git ls-files returned no files under infinitemarkets/")
    return files


def build_zip(version: str, files: list[str], out_dir: Path) -> Path:
    zip_path = out_dir / f"{EXT_DIR}-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            info = zipfile.ZipInfo(rel, date_time=FIXED_DATE)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, (ROOT / rel).read_bytes())
    return zip_path


def write_manifest(version: str, zip_name: str, sha256: str,
                   config: dict, out_dir: Path) -> Path:
    tag = f"v{version}"
    manifest = {
        "extensions": [
            {
                "id": EXT_DIR,
                "name": config["name"],
                "version": version,
                "archive": f"{REPO}/releases/download/{tag}/{zip_name}",
                "hash": sha256,
                "repo": REPO,
                "icon": None,
                "short_description": config["short_description"],
                "min_lnbits_version": config.get("min_lnbits_version"),
                "max_lnbits_version": config.get("max_lnbits_version"),
                "html_url": f"{REPO}/releases/tag/{tag}",
                "details_link": (
                    "https://raw.githubusercontent.com/bitkarrot/"
                    f"infinitemarkets/{tag}/{EXT_DIR}/config.json"
                ),
                "dependencies": [],
            }
        ],
        "repos": [],
        "featured": [],
        "categories": {},
    }
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def main() -> None:
    config = json.loads((ROOT / EXT_DIR / "config.json").read_text())
    version = config["version"]
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)

    files = tracked_files()
    zip_path = build_zip(version, files, out_dir)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    manifest_path = write_manifest(
        version, zip_path.name, digest, config, out_dir
    )

    print(f"zip:      {zip_path.relative_to(ROOT)} "
          f"({len(files)} files, {zip_path.stat().st_size} bytes)")
    print(f"sha256:   {digest}")
    print(f"manifest: {manifest_path.relative_to(ROOT)}")
    print("\nRelease commands:")
    print(f"  git tag v{version} && git push origin v{version}")
    print(f"  gh release create v{version} "
          f"dist/{zip_path.name} dist/manifest.json "
          f"--title 'infinitemarkets v{version}'")


if __name__ == "__main__":
    main()
