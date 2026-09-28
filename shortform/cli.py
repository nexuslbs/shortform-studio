"""Command-line interface: ``python -m shortform <cmd> [...]``."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .billing_cli import add_billing_subparser
from .measure import DEFAULT_MOCK_BASE, REAL_API_BASE as MEASURE_API_BASE, measure
from .produce import produce
from .publish import PRIVACY_CHOICES, REAL_API_BASE as PUBLISH_API_BASE, publish
from .qa import print_report, run_qa
from .util import NetworkError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m shortform",
        description="OmniStack ShortForm Studio - produce, QA, publish and measure "
        "policy-compliant 9:16 short videos.",
    )
    parser.add_argument("--version", action="version", version=f"shortform-studio {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_produce = sub.add_parser("produce", help="render out/<slug>/video.mp4 from content/<slug>/script.json")
    p_produce.add_argument("--slug", required=True)
    p_produce.add_argument("--seconds", type=float, default=None,
                           help="rescale scene holds so the video is this long")
    p_produce.set_defaults(func=_cmd_produce)

    p_qa = sub.add_parser("qa", help="validate the produced artifact (exit 0 PASS / 1 FAIL)")
    p_qa.add_argument("--slug", required=True)
    p_qa.set_defaults(func=_cmd_qa)

    p_pub = sub.add_parser("publish", help="YouTube resumable upload (dry-run by default)")
    p_pub.add_argument("--slug", required=True)
    mode = p_pub.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the request, send nothing (default)")
    mode.add_argument("--live", action="store_true", help="perform the real upload (needs $YOUTUBE_OAUTH_TOKEN)")
    p_pub.add_argument("--privacy", choices=PRIVACY_CHOICES, default="private")
    p_pub.add_argument("--api-base", default=PUBLISH_API_BASE,
                       help="override the API host (default: %(default)s)")
    p_pub.set_defaults(func=_cmd_publish)

    p_meas = sub.add_parser("measure", help="fetch statistics and append a metrics snapshot")
    p_meas.add_argument("--video-id", required=True)
    p_meas.add_argument("--mock", action="store_true",
                        help=f"use the local mock base URL (default {DEFAULT_MOCK_BASE})")
    p_meas.add_argument("--api-base", default=None,
                        help="override the API host (default: real Google host)")
    p_meas.set_defaults(func=_cmd_measure)

    add_billing_subparser(sub)

    return parser


def _cmd_produce(args) -> int:
    result = produce(args.slug, seconds=args.seconds)
    print(f"produced {result['video']} ({result['duration_s']:.3f}s, {result['scenes']} scenes)")
    print(f"provenance: {result['provenance']}")
    return 0


def _cmd_qa(args) -> int:
    report, code = run_qa(args.slug)
    print_report(report)
    return code


def _cmd_publish(args) -> int:
    mode = "live" if args.live else "dry-run"
    return publish(args.slug, mode=mode, privacy=args.privacy, api_base=args.api_base)


def _cmd_measure(args) -> int:
    api_base = args.api_base
    if args.mock and api_base is None:
        api_base = DEFAULT_MOCK_BASE
    return measure(args.video_id, mock=args.mock, api_base=api_base)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except NetworkError as exc:
        print(f"[NETWORK ERROR] {exc}", file=sys.stderr)
        return 3
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
