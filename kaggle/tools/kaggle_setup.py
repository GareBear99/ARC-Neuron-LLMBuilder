#!/usr/bin/env python3
"""Render per-user Kaggle metadata from the repo templates.

Bring your own Kaggle account (Gary, 2026-11-12): the repo ships
placeholders only — no account is named in it. This script fills in
YOUR Kaggle username from a local, gitignored config and stages the
complete dataset + notebook trees the Kaggle CLI consumes.

  1. cp kaggle/kaggle.local.json.example kaggle/kaggle.local.json
  2. Edit kaggle.local.json: put your Kaggle username in
     "kaggle_username" (the slugs stay as they are — they are the
     product names, not anyone's account).
  3. python3 kaggle/tools/kaggle_setup.py
  4. Run the exact `kaggle datasets ...` / `kaggle kernels push ...`
     commands it prints, pointed at the staged kaggle/.local/ trees.

Your Kaggle API token (kaggle.json) is separate: it lives in
~/.kaggle/kaggle.json on your own machine (chmod 600) and is never
in this repo, never in this config, never printed by this script.
Your GPU quota is yours — jobs you run spend your account's hours,
never anyone else's, and never Gary's.

The render is a plain text substitution of the "<kaggle-username>"
placeholder in the template files, so the staged metadata is
byte-identical to the template except for the owner. Validation
runs on the rendered files (JSON parses, required fields present,
ids shaped like owner/slug) — no push, no upload, nothing leaves
your machine here.

Env overrides (for verification, not for normal use):
  KAGGLE_LOCAL_CONFIG — config path (default kaggle/kaggle.local.json)
  KAGGLE_LOCAL_OUT    — staging dir (default kaggle/.local)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

PLACEHOLDER = "<kaggle-username>"
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SLUG_RE = re.compile(r"^[^/\s]+/[^/\s]+$")

DEFAULT_DATASET_SLUG = "llmbuilder-lora-run"
DEFAULT_KERNEL_SLUG = "llmbuilder-lora-train-t4-qlora-152-steps"

KAGGLE_ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            "kaggle_setup: no local config found.\n"
            "  cp kaggle/kaggle.local.json.example kaggle/kaggle.local.json\n"
            "  then put YOUR Kaggle username in \"kaggle_username\".\n"
            f"  (looked for {path})"
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"kaggle_setup: cannot read config {path}: {exc}") from exc
    if not isinstance(config, dict):
        raise SystemExit(f"kaggle_setup: config {path} must be a JSON object.")
    username = config.get("kaggle_username", "")
    if not isinstance(username, str) or not USERNAME_RE.match(username):
        raise SystemExit(
            "kaggle_setup: \"kaggle_username\" must be your Kaggle username "
            "(letters, digits, underscore, hyphen) — no placeholder, no slash."
        )
    for key, default in (
        ("dataset_slug", DEFAULT_DATASET_SLUG),
        ("kernel_slug", DEFAULT_KERNEL_SLUG),
    ):
        value = config.get(key, default)
        if not isinstance(value, str) or value.strip() == "" or "/" in value:
            raise SystemExit(f'kaggle_setup: "{key}" must be a plain slug name.')
        config[key] = value
    config["kaggle_username"] = username
    return config


def render_templates(config: dict) -> dict[str, str]:
    """Render the two metadata templates. Returns {relpath: text}."""
    username = config["kaggle_username"]
    rendered: dict[str, str] = {}
    for rel in (
        "dataset/dataset-metadata.json",
        "notebook/kernel-metadata.json",
    ):
        template_path = KAGGLE_ROOT / rel
        try:
            text = template_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SystemExit(
                f"kaggle_setup: cannot read template {template_path}: {exc}"
            ) from exc
        if PLACEHOLDER not in text:
            raise SystemExit(
                f"kaggle_setup: template {rel} has no {PLACEHOLDER} to fill in."
            )
        rendered[rel] = text.replace(PLACEHOLDER, username)
    return rendered


def validate_rendered(rendered: dict[str, str], config: dict) -> None:
    """Validate the rendered metadata the way the Kaggle CLI would
    need it: parses as JSON, required fields present, ids shaped
    like owner/slug, sources well-formed, code file present."""
    username = config["kaggle_username"]
    dataset = json.loads(rendered["dataset/dataset-metadata.json"])
    if dataset.get("id") != f"{username}/{config['dataset_slug']}":
        raise SystemExit("kaggle_setup: rendered dataset id is wrong.")
    if not isinstance(dataset.get("title"), str) or not dataset["title"]:
        raise SystemExit("kaggle_setup: rendered dataset has no title.")
    if not isinstance(dataset.get("licenses"), list) or not dataset["licenses"]:
        raise SystemExit("kaggle_setup: rendered dataset has no licenses.")
    kernel = json.loads(rendered["notebook/kernel-metadata.json"])
    if kernel.get("id") != f"{username}/{config['kernel_slug']}":
        raise SystemExit("kaggle_setup: rendered kernel id is wrong.")
    for field in ("code_file", "language", "kernel_type"):
        if not isinstance(kernel.get(field), str) or not kernel[field]:
            raise SystemExit(f"kaggle_setup: rendered kernel has no {field}.")
    if not (KAGGLE_ROOT / "notebook" / kernel["code_file"]).exists():
        raise SystemExit(
            f"kaggle_setup: kernel code file {kernel['code_file']} is missing."
        )
    for source in kernel.get("dataset_sources", []):
        if not isinstance(source, str) or not SLUG_RE.match(source):
            raise SystemExit(
                f"kaggle_setup: bad dataset source {source!r} in rendered kernel."
            )
    if kernel.get("dataset_sources", []) != [f"{username}/{config['dataset_slug']}"]:
        raise SystemExit("kaggle_setup: rendered kernel dataset source is wrong.")


def stage(rendered: dict[str, str], out_dir: Path) -> tuple[Path, Path]:
    """Copy the full dataset + notebook trees, then overwrite the
    two metadata files with the rendered text. Returns the staged
    dataset + notebook dirs."""
    dataset_dir = out_dir / "dataset"
    notebook_dir = out_dir / "notebook"
    for src, dst in (
        (KAGGLE_ROOT / "dataset", dataset_dir),
        (KAGGLE_ROOT / "notebook", notebook_dir),
    ):
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    (dataset_dir / "dataset-metadata.json").write_text(
        rendered["dataset/dataset-metadata.json"], encoding="utf-8"
    )
    (notebook_dir / "kernel-metadata.json").write_text(
        rendered["notebook/kernel-metadata.json"], encoding="utf-8"
    )
    return dataset_dir, notebook_dir


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    config_path = Path(
        os.environ.get("KAGGLE_LOCAL_CONFIG", str(KAGGLE_ROOT / "kaggle.local.json"))
    )
    out_dir = Path(
        os.environ.get("KAGGLE_LOCAL_OUT", str(KAGGLE_ROOT / ".local"))
    )
    try:
        config = load_config(config_path)
        rendered = render_templates(config)
        validate_rendered(rendered, config)
    except SystemExit as exc:
        if str(exc):
            print(str(exc), file=sys.stderr)
        return 2
    username = config["kaggle_username"]
    if check_only:
        print(f"Config OK for Kaggle user {username} (nothing written).")
        print(f"  dataset: {username}/{config['dataset_slug']}")
        print(f"  kernel:  {username}/{config['kernel_slug']}")
        return 0
    dataset_dir, notebook_dir = stage(rendered, out_dir)
    print(f"Staged for Kaggle user {username}:")
    print(f"  dataset:  {dataset_dir}  ({username}/{config['dataset_slug']})")
    print(f"  notebook: {notebook_dir}  ({username}/{config['kernel_slug']})")
    print("Run these with YOUR Kaggle API token in ~/.kaggle/kaggle.json:")
    print(f"  kaggle datasets create -p {dataset_dir}")
    print(f"  kaggle kernels push -p {notebook_dir}")
    print("Then in the Kaggle web UI: add the HF_TOKEN secret, confirm")
    print("Accelerator = GPU T4, then Run All. The run spends YOUR")
    print("account's GPU hours — never anyone else's.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
