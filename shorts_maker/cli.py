from __future__ import annotations

import argparse
import os
from pathlib import Path

from .render import render_video
from .script_parser import parse_script, validate_segments
from .utils import ShortsMakerError, ValidationError, set_verbose


def parse_size(value: str) -> tuple[int, int]:
    if "x" not in value.lower():
        raise argparse.ArgumentTypeError("--size must be in WIDTHxHEIGHT format")
    w_raw, h_raw = value.lower().split("x", 1)
    try:
        width = int(w_raw)
        height = int(h_raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--size must contain integer dimensions") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("--size width and height must be > 0")
    return width, height


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Template-based shorts auto builder")
    parser.add_argument("--script", required=True, help="Path to script.txt")
    parser.add_argument("--assets", required=True, help="Path to assets directory")
    parser.add_argument("--out", required=True, help="Output MP4 path")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--size", type=parse_size, default=(1080, 1920))
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--bgm", default=None, help="Optional BGM path")
    parser.add_argument("--voice", choices=["none", "edge", "openai"], default="none")
    parser.add_argument("--voice-lang", default="ko-KR")
    parser.add_argument("--voice-voice", default="ko-KR-SunHiNeural")
    parser.add_argument("--font", default=None, help="Optional subtitle font path (reserved)")
    parser.add_argument("--subtitle-pos", choices=["bottom", "center"], default="bottom")
    parser.add_argument("--safe-margin", type=float, default=0.08)
    parser.add_argument("--fade", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--verbose", action="store_true", help="Print FFmpeg/ffprobe commands")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.duration <= 0:
        raise ValidationError("--duration must be greater than 0")
    if args.fps <= 0:
        raise ValidationError("--fps must be greater than 0")
    if not (0 <= args.safe_margin < 0.5):
        raise ValidationError("--safe-margin must be in range [0, 0.5)")
    if args.fade < 0:
        raise ValidationError("--fade must be >= 0")

    script_path = Path(args.script)
    if not script_path.exists():
        raise ValidationError(f"Script file not found: {script_path}")
    assets_path = Path(args.assets)
    if not assets_path.exists() or not assets_path.is_dir():
        raise ValidationError(f"Assets directory not found: {assets_path}")
    if args.bgm and not Path(args.bgm).exists():
        raise ValidationError(f"BGM file not found: {args.bgm}")
    if args.font and not Path(args.font).exists():
        raise ValidationError(f"Font file not found: {args.font}")
    if args.voice == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise ValidationError("--voice openai 사용 시 OPENAI_API_KEY 환경 변수가 필요합니다.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        set_verbose(args.verbose)
        validate_args(args)
        segments = parse_script(args.script)
        validate_segments(segments, duration=args.duration)
        render_video(
            segments=segments,
            assets_dir=args.assets,
            out_path=args.out,
            size=args.size,
            fps=args.fps,
            seed=args.seed,
            duration=args.duration,
            subtitle_pos=args.subtitle_pos,
            safe_margin=args.safe_margin,
            bgm=args.bgm,
            voice=args.voice,
            voice_lang=args.voice_lang,
            voice_voice=args.voice_voice,
            font=args.font,
            fade=args.fade,
        )
    except ShortsMakerError as exc:
        parser.error(str(exc))

    return 0
