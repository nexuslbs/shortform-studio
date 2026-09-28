"""SQLite store for the growing, structured shortform-studio data.

The repository keeps only the schema and the migrations (this module). The
database lives under the configured data root, by default
``{OMNI_DIR}/data/artifacts/shortform-studio/studio.db``, and is never
committed.

Tables
------
``items``
    One row per content item (a ``content/<slug>/script.json``), with the full
    script kept losslessly in ``content_json``.
``renders``
    Append-only render events: ``artifact_dir``, ``bytes``, ``sha256``,
    ``duration_s``, ``resolution`` and the QA tallies. UPDATE and DELETE are
    blocked by triggers; a later QA run appends a new row rather than editing.
``qa_reports``
    One append-only row per QA check, linked to the render that produced it.
``publish_events``
    Append-only publish results (dry runs are not events).
``catalog_products``
    The storefront catalog contract, seeded from the ``storefront/catalog.json``
    SOURCE fixture and updated with provider ids learned at provisioning time.
``entitlements``
    One row per verified billing event/object (idempotent on ``event_id``).
``measurement_series``
    One row per metric sample written by ``measure``.
``schema_migrations`` / ``data_migrations``
    Applied schema versions and one-shot data imports.

``store migrate`` is the documented one-shot lossless import of the historical
``out/<slug>/`` tree into the data root plus ``items``/``renders``. ``store
verify`` re-hashes the files on disk and compares them to the ``renders`` rows.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

from . import paths

SCHEMA_VERSION = 1
DB_FILENAME = "studio.db"

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_FIXTURE = REPO_ROOT / "storefront" / "catalog.json"

_MIGRATIONS = {
    1: """
CREATE TABLE IF NOT EXISTS items (
    slug TEXT PRIMARY KEY,
    title TEXT,
    kind TEXT,
    price_cents INTEGER,
    currency TEXT,
    blurb TEXT,
    content_json TEXT,
    metadata_json TEXT,
    provider_product_id TEXT,
    provider_price_id TEXT,
    recurring_interval TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind);

CREATE TABLE IF NOT EXISTS renders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    slug TEXT NOT NULL,
    artifact_dir TEXT NOT NULL,
    bytes INTEGER,
    sha256 TEXT,
    duration_s REAL,
    resolution TEXT,
    qa_pass INTEGER,
    qa_total INTEGER,
    status TEXT
);
CREATE INDEX IF NOT EXISTS idx_renders_slug ON renders(slug);
CREATE TRIGGER IF NOT EXISTS renders_no_update
BEFORE UPDATE ON renders
BEGIN
    SELECT RAISE(ABORT, 'renders is append-only');
END;
CREATE TRIGGER IF NOT EXISTS renders_no_delete
BEFORE DELETE ON renders
BEGIN
    SELECT RAISE(ABORT, 'renders is append-only');
END;

CREATE TABLE IF NOT EXISTS qa_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    render_id INTEGER,
    check_name TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_qa_reports_render ON qa_reports(render_id);
CREATE TRIGGER IF NOT EXISTS qa_reports_no_update
BEFORE UPDATE ON qa_reports
BEGIN
    SELECT RAISE(ABORT, 'qa_reports is append-only');
END;
CREATE TRIGGER IF NOT EXISTS qa_reports_no_delete
BEFORE DELETE ON qa_reports
BEGIN
    SELECT RAISE(ABORT, 'qa_reports is append-only');
END;

CREATE TABLE IF NOT EXISTS publish_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    slug TEXT NOT NULL,
    platform TEXT,
    video_id TEXT,
    privacy TEXT,
    result_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_publish_events_slug ON publish_events(slug);
CREATE TRIGGER IF NOT EXISTS publish_events_no_update
BEFORE UPDATE ON publish_events
BEGIN
    SELECT RAISE(ABORT, 'publish_events is append-only');
END;
CREATE TRIGGER IF NOT EXISTS publish_events_no_delete
BEFORE DELETE ON publish_events
BEGIN
    SELECT RAISE(ABORT, 'publish_events is append-only');
END;

CREATE TABLE IF NOT EXISTS catalog_products (
    slug TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    amount_cents INTEGER,
    currency TEXT,
    recurring_interval TEXT,
    product_id TEXT,
    price_id TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS entitlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE,
    product_slug TEXT,
    order_id TEXT,
    subscription_id TEXT,
    checkout_id TEXT,
    amount_cents INTEGER,
    currency TEXT,
    created_at TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_entitlements_slug ON entitlements(product_slug);
CREATE TRIGGER IF NOT EXISTS entitlements_no_update
BEFORE UPDATE ON entitlements
BEGIN
    SELECT RAISE(ABORT, 'entitlements is append-only');
END;
CREATE TRIGGER IF NOT EXISTS entitlements_no_delete
BEFORE DELETE ON entitlements
BEGIN
    SELECT RAISE(ABORT, 'entitlements is append-only');
END;

CREATE TABLE IF NOT EXISTS measurement_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    slug TEXT NOT NULL,
    source TEXT,
    metric TEXT NOT NULL,
    value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_measurement_series_slug_metric
    ON measurement_series(slug, metric);
CREATE TRIGGER IF NOT EXISTS measurement_series_no_update
BEFORE UPDATE ON measurement_series
BEGIN
    SELECT RAISE(ABORT, 'measurement_series is append-only');
END;
CREATE TRIGGER IF NOT EXISTS measurement_series_no_delete
BEFORE DELETE ON measurement_series
BEGIN
    SELECT RAISE(ABORT, 'measurement_series is append-only');
END;

CREATE TABLE IF NOT EXISTS data_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
""",
}


def _now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def db_path() -> Path:
    return paths.db_path()


def connect(path=None) -> sqlite3.Connection:
    """Open the store, creating the data-root directory and applying migrations."""
    target = Path(path) if path is not None else db_path()
    if str(target) != ":memory:":
        target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    _apply_migrations(conn)
    return conn


def _apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for version in sorted(_MIGRATIONS):
        if version in applied:
            continue
        conn.executescript(_MIGRATIONS[version])
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, _now()),
        )
    conn.commit()


# --------------------------------------------------------------------------- #
# Items + catalog
# --------------------------------------------------------------------------- #

def upsert_item(slug: str, script: dict, conn: sqlite3.Connection = None) -> None:
    """Persist one content item; the full script is kept in ``content_json``."""
    own = conn is None
    if own:
        conn = connect()
    metadata = {
        key: script.get(key)
        for key in ("topic", "label", "tags", "hashtags", "categoryId")
    }
    try:
        conn.execute(
            "INSERT INTO items "
            "(slug, title, kind, price_cents, currency, blurb, content_json, "
            " metadata_json, recurring_interval, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET "
            "title=excluded.title, kind=excluded.kind, "
            "blurb=excluded.blurb, content_json=excluded.content_json, "
            "metadata_json=excluded.metadata_json, updated_at=excluded.updated_at",
            (
                str(slug),
                str(script.get("title") or ""),
                "video",
                None,
                None,
                str(script.get("summary") or ""),
                json.dumps(script, sort_keys=True),
                json.dumps(metadata, sort_keys=True),
                None,
                _now(),
            ),
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def catalog_fixture_path() -> Path:
    import os

    override = os.environ.get("SHORTFORM_STOREFRONT_CATALOG")
    return Path(override) if override else CATALOG_FIXTURE


def load_catalog_fixture(path=None) -> dict:
    """Load the SOURCE catalog fixture (env-overridable)."""
    target = Path(path) if path else catalog_fixture_path()
    with open(target, "r", encoding="utf-8") as handle:
        return json.load(handle)


def upsert_catalog(catalog: dict, conn: sqlite3.Connection = None) -> int:
    """Persist the catalog contract items (provider ids filled later)."""
    items = catalog.get("items") or []
    own = conn is None
    if own:
        conn = connect()
    try:
        for item in items:
            conn.execute(
                "INSERT INTO catalog_products "
                "(slug, name, description, amount_cents, currency, "
                " recurring_interval, product_id, price_id, active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(slug) DO UPDATE SET "
                "name=excluded.name, description=excluded.description, "
                "amount_cents=excluded.amount_cents, currency=excluded.currency, "
                "recurring_interval=excluded.recurring_interval, "
                "product_id=COALESCE(excluded.product_id, catalog_products.product_id), "
                "price_id=COALESCE(excluded.price_id, catalog_products.price_id), "
                "active=excluded.active",
                (
                    str(item.get("slug") or ""),
                    str(item.get("name") or item.get("title") or ""),
                    str(item.get("description") or item.get("blurb") or ""),
                    int(item.get("amount", item.get("price_cents")) or 0),
                    str(item.get("currency") or catalog.get("currency") or "usd"),
                    item.get("recurring_interval"),
                    item.get("product_id"),
                    item.get("price_id"),
                    1,
                ),
            )
        conn.commit()
    finally:
        if own:
            conn.close()
    return len(items)


def catalog_rows(conn: sqlite3.Connection = None) -> list:
    """Every ``catalog_products`` row, seeding from the fixture when empty."""
    own = conn is None
    if own:
        conn = connect()
    try:
        rows = conn.execute(
            "SELECT slug, name, description, amount_cents, currency, "
            "recurring_interval, product_id, price_id, active "
            "FROM catalog_products ORDER BY slug"
        ).fetchall()
        if not rows:
            catalog = load_catalog_fixture()
            upsert_catalog(catalog, conn=conn)
            rows = conn.execute(
                "SELECT slug, name, description, amount_cents, currency, "
                "recurring_interval, product_id, price_id, active "
                "FROM catalog_products ORDER BY slug"
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# Renders + QA + publish + measurements + entitlements
# --------------------------------------------------------------------------- #

def record_render(
    slug: str,
    artifact_dir,
    bytes: int = None,
    sha256: str = None,
    duration_s: float = None,
    resolution: str = None,
    qa_pass: int = None,
    qa_total: int = None,
    status: str = "rendered",
    ts: str = None,
    conn: sqlite3.Connection = None,
) -> int:
    """Append one render event; returns the new row id."""
    own = conn is None
    if own:
        conn = connect()
    try:
        cursor = conn.execute(
            "INSERT INTO renders "
            "(ts, slug, artifact_dir, bytes, sha256, duration_s, resolution, "
            " qa_pass, qa_total, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts or _now(),
                str(slug),
                str(artifact_dir),
                int(bytes) if bytes is not None else None,
                sha256,
                float(duration_s) if duration_s is not None else None,
                resolution,
                int(qa_pass) if qa_pass is not None else None,
                int(qa_total) if qa_total is not None else None,
                str(status or "rendered"),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        if own:
            conn.close()


def record_qa(
    slug: str,
    report: dict,
    artifact_dir,
    bytes: int = None,
    sha256: str = None,
    duration_s: float = None,
    resolution: str = None,
    conn: sqlite3.Connection = None,
) -> int:
    """Append a QA event: one ``renders`` row plus one ``qa_reports`` row per check."""
    checks = list(report.get("checks") or [])
    passed = sum(1 for check in checks if check.get("passed"))
    own = conn is None
    if own:
        conn = connect()
    try:
        render_id = record_render(
            slug,
            artifact_dir,
            bytes=bytes,
            sha256=sha256,
            duration_s=duration_s,
            resolution=resolution,
            qa_pass=passed,
            qa_total=len(checks),
            status="qa_pass" if report.get("pass") else "qa_fail",
            conn=conn,
        )
        for check in checks:
            conn.execute(
                "INSERT INTO qa_reports (render_id, check_name, passed, detail) "
                "VALUES (?, ?, ?, ?)",
                (
                    render_id,
                    str(check.get("check") or ""),
                    1 if check.get("passed") else 0,
                    str(check.get("detail") or ""),
                ),
            )
        conn.commit()
        return render_id
    finally:
        if own:
            conn.close()


def record_publish_event(
    slug: str,
    platform: str,
    video_id: str,
    privacy: str,
    result: dict,
    ts: str = None,
    conn: sqlite3.Connection = None,
) -> int:
    own = conn is None
    if own:
        conn = connect()
    try:
        cursor = conn.execute(
            "INSERT INTO publish_events "
            "(ts, slug, platform, video_id, privacy, result_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                ts or _now(),
                str(slug),
                str(platform),
                str(video_id or ""),
                str(privacy or ""),
                json.dumps(result or {}, sort_keys=True),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        if own:
            conn.close()


def record_measurements(
    slug: str,
    source: str,
    metrics: dict,
    ts: str = None,
    conn: sqlite3.Connection = None,
) -> int:
    """Append one ``measurement_series`` row per metric sample."""
    stamp = ts or _now()
    own = conn is None
    if own:
        conn = connect()
    try:
        count = 0
        for metric, value in sorted((metrics or {}).items()):
            conn.execute(
                "INSERT INTO measurement_series (ts, slug, source, metric, value) "
                "VALUES (?, ?, ?, ?, ?)",
                (stamp, str(slug), str(source or ""), str(metric), float(value or 0.0)),
            )
            count += 1
        conn.commit()
        return count
    finally:
        if own:
            conn.close()


def record_entitlement(event, env: str = "sandbox", conn: sqlite3.Connection = None) -> bool:
    """Upsert one entitlement from a verified billing event. True if inserted."""
    event_id = str(getattr(event, "id", "") or getattr(event, "object_id", "") or "")
    if not event_id:
        return False
    data = getattr(event, "data", None) or {}
    metadata = (data.get("metadata") or {}) if isinstance(data, dict) else {}
    own = conn is None
    if own:
        conn = connect()
    try:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO entitlements "
            "(event_id, product_slug, order_id, subscription_id, checkout_id, "
            " amount_cents, currency, created_at, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                str(metadata.get("slug") or "-"),
                str(getattr(event, "object_id", "") or ""),
                str(getattr(event, "subscription_id", "") or ""),
                str(getattr(event, "checkout_id", "") or ""),
                int(getattr(event, "amount_cents", 0) or 0),
                str((data.get("currency") if isinstance(data, dict) else None) or "usd"),
                _now(),
                json.dumps(getattr(event, "raw", None) or {}, sort_keys=True),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# Migration + verification
# --------------------------------------------------------------------------- #

def _migration_seen(version: str, conn: sqlite3.Connection) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM data_migrations WHERE version = ?", (version,)
        ).fetchone()
        is not None
    )


def _mark_migration(version: str, conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO data_migrations (version, applied_at) VALUES (?, ?)",
        (version, _now()),
    )
    conn.commit()


def migrate_legacy_out(
    source_root=None,
    content_root=None,
    slugs=None,
    dest_root=None,
    conn: sqlite3.Connection = None,
) -> dict:
    """One-shot lossless import of the historical ``out/<slug>/`` tree.

    Copies every file byte-identical into ``{data_root}/<slug>/``, imports
    ``content/<slug>/script.json`` into ``items`` and inserts one ``renders``
    row per slug. Idempotent per slug via ``data_migrations``.
    """
    source_root = Path(source_root) if source_root else REPO_ROOT / "out"
    content_root = Path(content_root) if content_root else REPO_ROOT / "content"
    own = conn is None
    if own:
        conn = connect()
    examined = 0
    inserted = 0
    results = []
    try:
        if slugs:
            candidates = [source_root / str(slug) for slug in slugs]
            candidates = [path for path in candidates if path.is_dir()]
        elif source_root.is_dir():
            candidates = sorted(path for path in source_root.iterdir() if path.is_dir())
        else:
            candidates = []

        for slug_dir in candidates:
            slug = slug_dir.name
            script_path = content_root / slug / "script.json"
            if not script_path.exists():
                # Not a content item (for example out/selftest); skip it.
                continue
            dest = paths.artifact_dir(slug, dest_root)

            file_count = 0
            for src in sorted(slug_dir.rglob("*")):
                if not src.is_file():
                    continue
                file_count += 1
                relative = src.relative_to(slug_dir)
                target = dest / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != src.read_bytes():
                    shutil.copy2(src, target)
            examined += file_count

            script = json.loads(script_path.read_text(encoding="utf-8"))
            upsert_item(slug, script, conn=conn)

            version = "legacy_out:%s:v1" % slug
            already = _migration_seen(version, conn)
            video = dest / "video.mp4"
            video_sha = sha256_file(video) if video.exists() else None
            video_bytes = video.stat().st_size if video.exists() else None
            duration_s, resolution, qa_pass, qa_total = _inspect_artifacts(dest)

            if not already:
                record_render(
                    slug,
                    dest,
                    bytes=video_bytes,
                    sha256=video_sha,
                    duration_s=duration_s,
                    resolution=resolution,
                    qa_pass=qa_pass,
                    qa_total=qa_total,
                    status="qa_pass" if qa_pass and qa_total and qa_pass == qa_total
                    else "imported",
                    conn=conn,
                )
                _mark_migration(version, conn)
                inserted += file_count

            results.append(
                {
                    "slug": slug,
                    "source": str(slug_dir),
                    "artifact_dir": str(dest),
                    "files": file_count,
                    "already_migrated": already,
                    "sha256": video_sha,
                    "bytes": video_bytes,
                }
            )

        return {
            "store_db": str(db_path()),
            "source_root": str(source_root),
            "examined": examined,
            "inserted": inserted,
            "results": results,
        }
    finally:
        if own:
            conn.close()


def _inspect_artifacts(dest: Path):
    """Best-effort duration/resolution/QA tallies from the copied artifacts."""
    duration_s = None
    resolution = None
    qa_pass = None
    qa_total = None
    probe_path = dest / "ffprobe.json"
    if probe_path.exists():
        try:
            probe = json.loads(probe_path.read_text(encoding="utf-8"))
            duration_s = float(probe.get("format", {}).get("duration") or 0.0) or None
            for stream in probe.get("streams", []):
                if stream.get("codec_type") == "video":
                    width, height = stream.get("width"), stream.get("height")
                    if width and height:
                        resolution = "%sx%s" % (width, height)
                    break
        except (ValueError, OSError):
            pass
    report_path = dest / "qa-report.json"
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            checks = report.get("checks") or []
            qa_pass = sum(1 for check in checks if check.get("passed"))
            qa_total = len(checks)
        except (ValueError, OSError):
            pass
    return duration_s, resolution, qa_pass, qa_total


def latest_renders(conn: sqlite3.Connection = None) -> list:
    """The most recent render row per slug (highest id wins)."""
    own = conn is None
    if own:
        conn = connect()
    try:
        rows = conn.execute("SELECT * FROM renders ORDER BY id").fetchall()
        latest = {}
        for row in rows:
            latest[row["slug"]] = row
        return [latest[key] for key in sorted(latest)]
    finally:
        if own:
            conn.close()


def verify_store(conn: sqlite3.Connection = None) -> dict:
    """Compare every latest ``renders`` row against the file on disk.

    Matches ``sha256`` AND ``bytes``; a missing file, a length mismatch or a
    hash mismatch fails. Returns a dict with ``match`` and per-slug detail.
    """
    own = conn is None
    if own:
        conn = connect()
    try:
        checks = []
        match = True
        for row in latest_renders(conn):
            video = Path(row["artifact_dir"]) / "video.mp4"
            exists = video.exists()
            size = video.stat().st_size if exists else None
            digest = sha256_file(video) if exists else None
            ok = bool(
                exists
                and digest == row["sha256"]
                and (row["bytes"] is None or size == row["bytes"])
            )
            match = match and ok
            checks.append(
                {
                    "slug": row["slug"],
                    "path": str(video),
                    "db_sha256": row["sha256"],
                    "disk_sha256": digest,
                    "db_bytes": row["bytes"],
                    "disk_bytes": size,
                    "match": ok,
                    "status": row["status"],
                    "qa": "%s/%s" % (row["qa_pass"], row["qa_total"]),
                }
            )
        return {
            "store_db": str(db_path()),
            "renders": len(checks),
            "checks": checks,
            "match": match,
        }
    finally:
        if own:
            conn.close()
