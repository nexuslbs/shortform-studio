"""Pytest configuration for the shortform-studio suite.

Runtime data defaults OUTSIDE the repository. Point the whole test session at a
throwaway data root before any test module imports ``shortform``, so a test that
forgets to redirect a writer can never dirty the real store or the repo tree.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

_TMP_DATA_ROOT = tempfile.mkdtemp(prefix="shortform-test-artifacts-")
os.environ["SHORTFORM_ARTIFACTS_DIR"] = _TMP_DATA_ROOT
atexit.register(shutil.rmtree, _TMP_DATA_ROOT, ignore_errors=True)
