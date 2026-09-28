#!/usr/bin/env python3
"""Host-side verification of the storefront artifact manifest.

A Cloudflare Worker has no host filesystem and the deployed Worker serves only
a JSON manifest (no bytes). This script is the host-side counterpart: it reads
``storefront/catalog.json`` (and checks the same locator embedded in
``storefront/worker/worker.js``), resolves the ``data://shortform-studio/...``
locator against the configured data root, re-hashes the file on disk and
compares it with the manifest AND, when present, the latest ``renders`` row in
the SQLite store.

Exit 0 when every manifest entry resolves, exists and matches; non-zero
otherwise. Nothing is deployed and no network call is made.

Usage:
    python3 storefront/scripts/verify_manifest.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from shortform import paths, store  # noqa: E402


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_render_for(conn, slug: str):
    rows = store.latest_renders(conn)
    for row in rows:
        if row["slug"] == slug:
            return row
    return None


def main() -> int:
    catalog_path = REPO / "storefront" / "catalog.json"
    worker_path = REPO / "storefront" / "worker" / "worker.js"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    worker_source = worker_path.read_text(encoding="utf-8")

    print("DATA_ROOT=%s" % paths.data_root())
    print("STORE_DB=%s" % store.db_path())

    failures = 0
    checked = 0
    conn = store.connect()
    try:
        for item in catalog.get("items", []):
            artifact = item.get("artifact")
            if not artifact:
                continue
            checked += 1
            locator = artifact["path"]
            slug = locator[len(paths.LOCATOR_PREFIX):].split("/", 1)[0]
            resolved = paths.resolve_locator(locator)
            exists = resolved.exists()
            disk_bytes = resolved.stat().st_size if exists else None
            disk_sha = _sha256(resolved) if exists else None
            bytes_ok = exists and disk_bytes == artifact.get("bytes")
            sha_ok = exists and disk_sha == artifact.get("sha256")
            worker_ok = locator in worker_source
            render = _latest_render_for(conn, slug)
            db_ok = True
            if render is not None:
                db_ok = (
                    render["sha256"] == artifact.get("sha256")
                    and render["bytes"] == artifact.get("bytes")
                )
            ok = exists and bytes_ok and sha_ok and worker_ok and db_ok
            failures += 0 if ok else 1
            print(
                "slug=%s locator=%s resolved=%s exists=%s bytes_ok=%s sha256_ok=%s "
                "worker_matches=%s db_matches=%s"
                % (item.get("slug"), locator, resolved, exists, bytes_ok, sha_ok,
                   worker_ok, db_ok)
            )
            if disk_sha:
                print("  manifest_sha256=%s" % artifact.get("sha256"))
                print("  disk_sha256=%s" % disk_sha)
            else:
                print("  manifest_sha256=%s" % artifact.get("sha256"))
                print("  disk_sha256=<missing>")
    finally:
        conn.close()

    print("artifacts=%d failures=%d MATCH=%s" % (checked, failures, failures == 0))
    return 0 if failures == 0 and checked > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
