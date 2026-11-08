"""apache_store.py — ARC Apache v5, called ONLY through its CLI contract.

This module is the ARC Apache side of the packet store. It does NOT
import arc_apache and does NOT copy its pack/verify logic. Every
operation is a subprocess call to ARC-Apache's own CLI entry point
(``scripts/arc_apache.py``), with the store path passed explicitly.
If ARC-Apache's CLI is missing or fails, the operation fails loudly —
it never silently falls back to a local reimplementation.

Contract (verified live against ARC-Apache 0.5.1, v5 format):
  pack <file> --store <store> --content-class instant_reply
      --codec arc-json-canonical
      -> manifest JSON with manifest_sha256, envelope_sha256,
         merkle_root, chunks[] (per-chunk SHA-256).
  verify <manifest> --store <store>  -> {"ok": bool, "errors": []}
  restore <manifest> <output> --store <store>  -> byte-identical bytes.
  receipt <manifest> --store <store> --source instant-reply-pack
      -> receipt JSON with receipt_path.
  bundle-plan --name <n> --manifest <m> [--receipt <r>] --out <file>

The store root (``apache_root``) is the ARC-Apache repo checkout by
default (~/workspace/ARC-Apache, overridable with the ARC_APACHE_ROOT
env var or the constructor argument). The packet store itself
(``store`` argument) is a separate directory — the .arc_apache store
holding manifests/chunks/receipts — never the ARC-Apache repo itself.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .packets import packet_bytes

DEFAULT_APACHE_ROOT = Path.home() / "workspace" / "ARC-Apache"


class ApacheNotAvailable(RuntimeError):
    """ARC-Apache's CLI entry point is missing — the store cannot run."""


class ApacheStore:
    """Thin subprocess wrapper around the ARC Apache v5 CLI."""

    def __init__(self, apache_root: Path | str | None = None) -> None:
        root = Path(apache_root or os.environ.get("ARC_APACHE_ROOT", DEFAULT_APACHE_ROOT))
        cli = root / "scripts" / "arc_apache.py"
        if not cli.is_file():
            raise ApacheNotAvailable(
                f"ARC-Apache CLI not found at {cli} — set ARC_APACHE_ROOT "
                "to the ARC-Apache checkout; the store never reimplements pack/verify"
            )
        self.apache_root = root
        self.cli = cli

    def _run(self, *args: str, cwd: Path | None = None) -> dict:
        proc = subprocess.run(
            ["python3", str(self.cli), *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"ARC-Apache CLI failed ({' '.join(args[:1])}): "
                f"rc={proc.returncode} stderr={proc.stderr.strip()[-500:]}"
            )
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"ok": True, "stdout": proc.stdout}

    def init_store(self, store: Path) -> dict:
        return self._run("init-store", "--store", str(store))

    def pack_packet(self, packet, store: Path) -> dict:
        """Pack one packet's canonical bytes as an ARC v5 payload.

        ``packet`` is a Packet (packets.py). Returns the manifest dict
        ARC-Apache produced (manifest_sha256, envelope_sha256,
        merkle_root, chunks). The packet bytes are written to a temp
        file first — the CLI packs files, and the packet's canonical
        bytes ARE the file.
        """
        from .packets import packet_id

        raw = packet_bytes(packet)
        store = Path(store)
        store.mkdir(parents=True, exist_ok=True)
        tmp = store / f".packet-{packet_id(packet)[:16]}.json"
        tmp.write_bytes(raw)
        try:
            result = self._run(
                "pack",
                str(tmp),
                "--store",
                str(store),
                "--content-class",
                "instant_reply",
                "--codec",
                "arc-json-canonical",
            )
        finally:
            tmp.unlink(missing_ok=True)
        manifest_path = Path(result["manifest_path"])
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def verify_manifest(self, manifest: dict, store: Path) -> tuple[bool, list[str]]:
        """Verify a manifest against the store. Returns (ok, errors)."""
        manifest_path = Path(store) / "manifests" / f"{manifest['manifest_sha256']}.json"
        result = self._run("verify", str(manifest_path), "--store", str(store))
        return bool(result.get("ok")), list(result.get("errors", []))

    def restore_packet(self, manifest: dict, store: Path, output: Path) -> Path:
        """Restore a packet's bytes from the store, byte-identical."""
        manifest_path = Path(store) / "manifests" / f"{manifest['manifest_sha256']}.json"
        self._run("restore", str(manifest_path), str(output), "--store", str(store))
        return Path(output)

    def receipt_for(self, manifest: dict, store: Path, *, source: str = "instant-reply-pack") -> dict:
        """Issue a receipt for a packed manifest. Returns the receipt dict."""
        manifest_path = Path(store) / "manifests" / f"{manifest['manifest_sha256']}.json"
        result = self._run(
            "receipt",
            str(manifest_path),
            "--store",
            str(store),
            "--source",
            source,
        )
        receipt_path = Path(result["receipt_path"])
        return json.loads(receipt_path.read_text(encoding="utf-8"))

    def bundle_plan(
        self,
        *,
        name: str,
        manifest_paths: list[Path],
        receipt_paths: list[Path],
        out: Path,
    ) -> dict:
        """Build an Arc-RAR bundle PLAN (proof plan, not the archive itself).

        The plan is what Arc-RAR turns into a portable archive — see
        arcrar.py, which builds the archive itself from the same
        manifests + receipts.
        """
        args: list[str] = ["bundle-plan", "--name", name, "--out", str(out)]
        for p in manifest_paths:
            args += ["--manifest", str(p)]
        for p in receipt_paths:
            args += ["--receipt", str(p)]
        self._run(*args)
        return json.loads(Path(out).read_text(encoding="utf-8"))
