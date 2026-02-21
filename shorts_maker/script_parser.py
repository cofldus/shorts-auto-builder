from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .utils import ValidationError, ensure_path_exists


@dataclass(frozen=True)
class Segment:
    index: int
    start: float
    end: float
    subtitle: str | None = None
    narration: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


def _parse_timestamp(value: str) -> float:
    raw = value.strip()
    if not raw:
        raise ValidationError("Timestamp cannot be empty")

    parts = raw.split(":")
    try:
        if len(parts) == 1:
            seconds = float(parts[0])
        elif len(parts) == 2:
            minutes = int(parts[0])
            sec = float(parts[1])
            seconds = minutes * 60 + sec
        elif len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            sec = float(parts[2])
            seconds = hours * 3600 + minutes * 60 + sec
        else:
            raise ValidationError(f"Invalid timestamp format: {value}")
    except ValueError as exc:
        raise ValidationError(f"Invalid timestamp value: {value}") from exc

    if seconds < 0:
        raise ValidationError(f"Timestamp must be >= 0: {value}")
    return seconds


def _split_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _parse_block(block: str, block_index: int) -> Segment:
    data: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            raise ValidationError(
                f"Segment {block_index + 1}: expected 'key: value' line, got: {line!r}"
            )
        key, value = line.split(":", 1)
        key_norm = key.strip().lower()
        value_norm = value.strip()
        if key_norm not in {"start", "end", "subtitle", "narration"}:
            raise ValidationError(
                f"Segment {block_index + 1}: unknown key '{key_norm}'. "
                "Allowed keys: start, end, subtitle, narration"
            )
        if key_norm in data:
            raise ValidationError(
                f"Segment {block_index + 1}: duplicate key '{key_norm}'"
            )
        data[key_norm] = value_norm

    if "start" not in data or "end" not in data:
        raise ValidationError(
            f"Segment {block_index + 1}: missing required keys 'start' and/or 'end'"
        )

    start = _parse_timestamp(data["start"])
    end = _parse_timestamp(data["end"])

    subtitle = data.get("subtitle") or None
    narration = data.get("narration") or None

    return Segment(
        index=block_index,
        start=start,
        end=end,
        subtitle=subtitle,
        narration=narration,
    )


def validate_segments(segments: Iterable[Segment], duration: float | None = None) -> None:
    items = list(segments)
    if not items:
        raise ValidationError("Script must contain at least one segment")

    for i, seg in enumerate(items):
        if seg.end <= seg.start:
            raise ValidationError(
                f"Segment {i + 1}: end ({seg.end}) must be greater than start ({seg.start})"
            )
        if i > 0:
            prev = items[i - 1]
            if seg.start < prev.start:
                raise ValidationError(
                    f"Segment {i + 1}: segments must be ordered by start time"
                )
            if seg.start < prev.end:
                raise ValidationError(
                    f"Segment {i + 1}: overlaps previous segment "
                    f"(prev end={prev.end}, start={seg.start})"
                )

    if duration is not None:
        if duration <= 0:
            raise ValidationError("Duration must be greater than 0")
        last_end = items[-1].end
        if last_end > duration:
            raise ValidationError(
                f"Last segment end ({last_end}) exceeds requested duration ({duration})"
            )


def parse_script(path: str | Path) -> list[Segment]:
    script_path = Path(path)
    ensure_path_exists(script_path, "script file")
    text = script_path.read_text(encoding="utf-8")
    blocks = _split_blocks(text)
    if not blocks:
        raise ValidationError("Script file contains no segments")

    segments = [_parse_block(block, i) for i, block in enumerate(blocks)]
    validate_segments(segments)
    return segments
