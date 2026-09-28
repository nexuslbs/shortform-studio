"""Runtime data locations for shortform-studio.

The repository is source-only: code, scripts, tests, small seed fixtures
(``content/<slug>/script.json`` and ``storefront/catalog.json``) and docs.
Every runtime or generated file lives under ONE configurable data root, resolved
in this order:

1. ``SHORTFORM_ARTIFACTS_DIR`` (full override, highest priority);
2. ``{OMNI_DIR}/data/artifacts/shortform-studio``, where ``OMNI_DIR`` defaults
   to ``/opt/omni``. An ``OMNI_DIR`` that already ends in ``data`` (for example
   ``/opt/omni/data``) is used as the base and does NOT get a second ``data``
   segment.

Nothing here ever defaults inside the repository tree.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_ARTIFACTS_DIR = "SHORTFORM_ARTIFACTS_DIR"
ENV_OMNI_DIR = "OMNI_DIR"
DEFAULT_OMNI_DIR = "/opt/omni"

#: Project subdirectory under the data root. One project, one sandbox tree.
PROJECT_SUBDIR = "shortform-studio"

#: Locator scheme used by the storefront manifest for host-side resolution.
#: A Cloudflare Worker has no filesystem; the manifest carries a locator so a
#: host-side tool can resolve it to the real data root and verify the bytes.
LOCATOR_SCHEME = "data://"
LOCATOR_PREFIX = LOCATOR_SCHEME + PROJECT_SUBDIR + "/"


def data_root() -> Path:
    """Return the resolved runtime data root (never inside the repo)."""
    override = os.environ.get(ENV_ARTIFACTS_DIR)
    if override:
        return Path(override).expanduser()
    omni = Path(os.environ.get(ENV_OMNI_DIR) or DEFAULT_OMNI_DIR).expanduser()
    if omni.name == "data":
        return omni / "artifacts" / PROJECT_SUBDIR
    return omni / "data" / "artifacts" / PROJECT_SUBDIR


def artifact_dir(slug: str, root: Path | None = None) -> Path:
    """Return the artifact directory for ``slug``.

    ``root`` is an explicit test/DI override for the *data root* (not the repo);
    when omitted the configured data root is used.
    """
    base = Path(root) if root is not None else data_root()
    return base / str(slug)


def measurements_dir(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else data_root()
    return base / "measurements"


def db_path() -> Path:
    """The SQLite store file, ``{data_root}/studio.db`` (never committed)."""
    return data_root() / "studio.db"


def locator_for(slug: str, name: str = "video.mp4") -> str:
    """Build the storefront locator for an artifact, for example
    ``data://shortform-studio/roman-concrete/video.mp4``.
    """
    return f"{LOCATOR_PREFIX}{slug}/{name}"


def resolve_locator(locator: str, root: Path | None = None) -> Path:
    """Resolve a ``data://shortform-studio/<slug>/<name>`` locator to a path.

    Raises :class:`ValueError` for any other scheme or project so a
    misconfigured manifest fails loudly instead of silently reading the repo.
    """
    text = str(locator or "")
    if not text.startswith(LOCATOR_PREFIX):
        raise ValueError(
            "unsupported artifact locator %r (expected prefix %r)"
            % (text, LOCATOR_PREFIX)
        )
    relative = text[len(LOCATOR_PREFIX):].lstrip("/")
    if not relative:
        raise ValueError("artifact locator has no relative path: %r" % text)
    base = Path(root) if root is not None else data_root()
    return base / relative
