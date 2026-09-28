# ARTIFACT-STORE - shortform-studio storage contract

How ShortForm Studio separates repository SOURCE from runtime/generated data.

## Rule

The repository contains only source: the `shortform/` package, scripts, tests,
the Worker and its scripts, docs, small seed fixtures
(`content/<slug>/script.json`, `storefront/catalog.json`) and CI/config. Every
runtime or generated file lives under one configurable data root, never in the
repo tree.

This is the same contract the P1 `asset-pipeline` uses (`assetpipeline/paths.py`,
`assetpipeline/store.py`, `docs/DATA-STORE.md`); the shape is reused here rather
than inventing a second idiom.

## Data root

Resolution order (`shortform/paths.py`):

1. `$SHORTFORM_ARTIFACTS_DIR` (full override, highest priority);
2. `{OMNI_DIR}/data/artifacts/shortform-studio`, `OMNI_DIR` defaulting to
   `/opt/omni`. An `OMNI_DIR` that already ends in `/data` (for example
   `/opt/omni/data`) is used as the base WITHOUT a second `data` segment.

The default is `/opt/omni/data/artifacts/shortform-studio/`. Nothing defaults
inside the repository tree. Print the resolved paths with:

```bash
python3 -m shortform store path
# DATA_ROOT=... STORE_DB=... MEASUREMENTS_DIR=...
```

## Layout under the data root

```
{data_root}/
  <slug>/video.mp4              rendered artifact (plus captions, metadata, ...)
  <slug>/qa-report.json         QA evidence (also recorded in qa_reports)
  studio.db                     the SQLite store (schema lives in-repo)
  measurements/<video>.jsonl    JSONL mirror of measurement_series
  ledger/ledger.jsonl           append-only billing mirror of entitlements
  selftest/                     raw evidence from scripts/selftest.sh
```

## SQLite schema (`shortform/store.py`)

| Table | Contents |
|---|---|
| `items` | one row per `content/<slug>/script.json`; the full script is kept losslessly in `content_json` |
| `renders` | append-only render/QA events: `artifact_dir`, `bytes`, `sha256`, `duration_s`, `resolution`, `qa_pass`, `qa_total`, `status` |
| `qa_reports` | one append-only row per QA check, linked to a render |
| `publish_events` | append-only publish results (dry runs are not events) |
| `catalog_products` | the storefront catalog contract, seeded from the SOURCE fixture and updated with provider ids |
| `entitlements` | one row per verified billing event (`event_id` unique), append-only |
| `measurement_series` | one append-only row per metric sample |
| `schema_migrations` / `data_migrations` | applied schema versions and one-shot imports |

`renders`, `qa_reports`, `publish_events`, `entitlements` and
`measurement_series` have `BEFORE UPDATE` / `BEFORE DELETE` triggers that
`RAISE(ABORT)`, mirroring the P1 `ledger_events` contract. The schema and
migrations are repository source; the database file is runtime data and is never
committed (`*.sqlite3`, `*.sqlite3-wal`, `*.sqlite3-shm` are gitignored).

## Reading the catalog

`storefront/catalog.json` is a small SOURCE seed fixture. At runtime the billing
module reads `catalog_products` (via `shortform.billing.catalog.specs()`); when
the table is empty it is seeded from the fixture first. Provider ids learned at
provisioning time live in the store. An operator can point at a
different fixture with `$SHORTFORM_STOREFRONT_CATALOG`.

## Storefront artifact locator (host-side verification)

The storefront manifest does NOT contain a repository path. It carries a
data-store locator:

```json
"artifact": {
  "path": "data://shortform-studio/roman-concrete/video.mp4",
  "bytes": 2404763,
  "duration_s": 37.5,
  "resolution": "1080x1920",
  "qa": "17/17",
  "sha256": "9ce0e04e..."
}
```

Honest limitation: a Cloudflare Worker has no host filesystem, and the deployed
Worker serves only a JSON manifest (no bytes). The `data://` locator is resolved
on the HOST, not by the Worker. `storefront/scripts/verify_manifest.py` reads
`storefront/catalog.json`, checks the same locator is embedded in
`worker/worker.js`, resolves it against the configured data root, re-hashes the
file and compares it to the manifest and to the latest `renders` row:

```bash
python3 storefront/scripts/verify_manifest.py
# exit 0 only when every artifact exists and matches
```

## Migrating the legacy `out/` tree

```bash
python3 -m shortform store migrate    # one-shot, idempotent per slug
python3 -m shortform store verify     # re-hash disk vs renders, exit non-zero on mismatch
```

`store migrate` copies `out/<slug>/**` byte-identical into
`{data_root}/<slug>/`, imports `content/<slug>/script.json` into `items` and
inserts the `renders` row. It is idempotent through `data_migrations`.

### Executed migration evidence (2026-09-28)

The legacy tracked tree was imported BEFORE it was removed from git:

```text
STORE_DB=/opt/omni/data/artifacts/shortform-studio/studio.db
SOURCE=/opt/workspace/shortform-studio/out
examined=15 inserted=15
slug=roman-concrete files=15 already_migrated=False bytes=2404763 \
  sha256=9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206
```

`sha256sum {data_root}/roman-concrete/video.mp4` equals
`9ce0e04ef5fe79fb27ec10fd2eb16efedc024b9dbe48d1c62827b45f8dfff206` and the
size is `2404763` bytes, byte-identical to the removed tracked file.

## Small SOURCE fixtures that stay in the repo

| File | Why it stays |
|---|---|
| `content/<slug>/script.json` | The original script input read by `produce`; it is the content item and never written at runtime. |
| `storefront/catalog.json` | The catalog contract/seed: 4 items, read by the storefront and the billing module; never written at runtime. |
| `storefront/ledger/.gitkeep` | Keeps the runtime ledger directory present; the rows themselves (`*.jsonl`) are gitignored. |

No generated media or `out/`-style sink is tracked.
