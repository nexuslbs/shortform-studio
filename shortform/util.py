"""Shared helpers: paths, subprocess execution, hashing, ffprobe and loudness.

Everything here is stdlib-only except an optional Pillow import used elsewhere.
No credential is ever read here; credentials are read from the environment by
the modules that actually talk to the network (publish/measure).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import paths


class NetworkError(RuntimeError):
    """A non-HTTP network failure (DNS, refused connection, timeout, ...).

    Raised by the HTTP helpers in ``measure``/``publish`` so the CLI can report a
    single clean ``[NETWORK ERROR]`` line and exit 3 instead of dumping a raw
    traceback. HTTP-level failures (``urllib.error.HTTPError``) are *not* wrapped
    here; they carry a status code and are handled by the caller.
    """


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

def repo_root() -> Path:
    """Return the repository root (the directory that contains this package)."""
    return Path(__file__).resolve().parent.parent


def out_dir(slug: str, root: Path | None = None) -> Path:
    """Runtime artifact directory for ``slug``.

    Always resolves under the external data root (see :mod:`shortform.paths`)
    and never inside the repository tree. ``root`` is an explicit test/DI
    override for the *data root*; callers must pass ``None`` in production.
    """
    return paths.artifact_dir(slug, root)


def content_dir(slug: str, root: Path | None = None) -> Path:
    root = root or repo_root()
    return root / "content" / slug


# --------------------------------------------------------------------------- #
# Small filesystem/json helpers
# --------------------------------------------------------------------------- #

def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Command execution + provenance
# --------------------------------------------------------------------------- #

@dataclass
class CommandRecord:
    argv: list[str]
    cwd: str
    exit_code: int
    started_at: str
    duration_s: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "argv": self.argv,
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 3),
        }


@dataclass
class Provenance:
    """Collects every input, every command and every output hash for a run."""

    slug: str
    generated_at: str = ""
    inputs: list[dict[str, Any]] = field(default_factory=list)
    commands: list[CommandRecord] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    tools: dict[str, str] = field(default_factory=dict)

    def add_input(self, role: str, path: Path, text: str | None = None) -> None:
        entry: dict[str, Any] = {
            "role": role,
            "path": str(path),
            "sha256": sha256_file(path) if path.exists() else None,
        }
        if text is not None:
            entry["sha256_text"] = sha256_bytes(text.encode("utf-8"))
        self.inputs.append(entry)

    def add_output(self, role: str, path: Path) -> None:
        self.outputs.append(
            {
                "role": role,
                "path": str(path),
                "sha256": sha256_file(path) if path.exists() else None,
                "bytes": path.stat().st_size if path.exists() else None,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "generated_at": self.generated_at,
            "tools": self.tools,
            "inputs": self.inputs,
            "commands": [c.as_dict() for c in self.commands],
            "outputs": self.outputs,
        }


def run_cmd(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    provenance: Provenance | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, optionally tee-ing stdout/stderr to files.

    Every invocation is recorded in ``provenance`` (if given) so the produced
    ``provenance.json`` can name the exact tool calls that built the artifact.
    """
    argv = [str(a) for a in argv]
    started = time.time()
    proc = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    duration = time.time() - started
    if stdout_path is not None:
        write_text(stdout_path, proc.stdout.decode("utf-8", "replace"))
    if stderr_path is not None:
        write_text(stderr_path, proc.stderr.decode("utf-8", "replace"))
    if provenance is not None:
        provenance.commands.append(
            CommandRecord(
                argv=argv,
                cwd=str(cwd) if cwd else os.getcwd(),
                exit_code=proc.returncode,
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                duration_s=duration,
            )
        )
    if check and proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace")[-4000:]
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(argv)}\n--- stderr tail ---\n{tail}"
        )
    return proc


def run_shell(
    command: str,
    *,
    cwd: Path | None = None,
    provenance: Provenance | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    started = time.time()
    proc = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if provenance is not None:
        provenance.commands.append(
            CommandRecord(
                argv=["/bin/sh", "-c", command],
                cwd=str(cwd) if cwd else os.getcwd(),
                exit_code=proc.returncode,
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                duration_s=time.time() - started,
            )
        )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"shell command failed ({proc.returncode}): {command}\n"
            f"--- stderr tail ---\n{proc.stderr.decode('utf-8', 'replace')[-4000:]}"
        )
    return proc


# --------------------------------------------------------------------------- #
# ffprobe / ffmpeg measurement
# --------------------------------------------------------------------------- #

def which(tool: str) -> str | None:
    return shutil.which(tool)


def require_tools(tools: Iterable[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    missing: list[str] = []
    for tool in tools:
        path = which(tool)
        if path is None:
            missing.append(tool)
        else:
            found[tool] = path
    if missing:
        raise RuntimeError(
            "missing required tool(s): "
            + ", ".join(missing)
            + "\nInstall with: apt-get update && apt-get install -y ffmpeg espeak-ng"
        )
    return found


def ffprobe_json(path: Path) -> dict[str, Any]:
    proc = run_cmd(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(proc.stdout.decode("utf-8", "replace"))


# ebur128 prints a "Summary:" block that is the last JSON-ish chunk in stderr.
_SUMMARY_RE = re.compile(r"Summary:\s*(\{.*?\})\s*(?:\n\s*\[|\Z)", re.S)
_INTEGRATED_RE = re.compile(r"^\s*I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", re.M)
_LRA_RE = re.compile(r"^\s*LRA:\s*(-?\d+(?:\.\d+)?)\s*LU", re.M)
_PEAK_RE = re.compile(r"^\s*Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", re.M)


def measure_loudness(path: Path) -> dict[str, float]:
    """Return integrated LUFS / LRA / true-peak dBFS using ffmpeg ebur128."""
    proc = run_cmd(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        check=True,
    )
    err = proc.stderr.decode("utf-8", "replace")
    out: dict[str, float] = {}
    match = _SUMMARY_RE.search(err)
    if match:
        try:
            data = json.loads(match.group(1))
            out["integrated_lufs"] = float(data.get("integrated_loudness", "nan"))
            out["lra_lu"] = float(data.get("loudness_range", "nan"))
            out["true_peak_dbfs"] = float(data.get("true_peak", "nan"))
            return out
        except (ValueError, json.JSONDecodeError):
            pass
    # fallback: parse the human-readable summary lines
    m = _INTEGRATED_RE.search(err)
    if m:
        out["integrated_lufs"] = float(m.group(1))
    m = _LRA_RE.search(err)
    if m:
        out["lra_lu"] = float(m.group(1))
    m = _PEAK_RE.search(err)
    if m:
        out["true_peak_dbfs"] = float(m.group(1))
    if not out:
        raise RuntimeError("could not parse ebur128 output:\n" + err[-2000:])
    return out


_LOUDNORM_JSON_RE = re.compile(r"\{\s*\"input_i\".*?\n\}", re.S)


def loudnorm_measure(path: Path) -> dict[str, str]:
    """First-pass loudnorm measurement (returns the printed JSON object)."""
    proc = run_cmd(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        check=True,
    )
    err = proc.stderr.decode("utf-8", "replace")
    match = _LOUDNORM_JSON_RE.search(err)
    if not match:
        raise RuntimeError("loudnorm did not print JSON:\n" + err[-2000:])
    return json.loads(match.group(0))


def loudnorm_second_pass(src: Path, dst: Path, measured: dict[str, str]) -> None:
    af = (
        "loudnorm=I=-14:TP=-1.5:LRA=11"
        f":measured_I={measured['input_i']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        ":linear=true:print_format=summary"
    )
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-i",
            str(src),
            "-af",
            af,
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(dst),
        ],
        check=True,
    )
