from pathlib import Path

import pytest

from shorts_maker.script_parser import parse_script
from shorts_maker.utils import ValidationError


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "script.txt"
    path.write_text(content, encoding="utf-8")
    return path


def test_overlapping_segments_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "start: 00:00\nend: 00:05\n\nstart: 00:04\nend: 00:08\n",
    )
    with pytest.raises(ValidationError, match="overlaps"):
        parse_script(path)


def test_missing_required_fields_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "start: 00:00\nsubtitle: missing end\n",
    )
    with pytest.raises(ValidationError, match="missing required"):
        parse_script(path)


def test_valid_script_ok(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "start: 00:00\nend: 00:03\nsubtitle: hello\n\nstart: 00:03\nend: 00:06\n",
    )
    segments = parse_script(path)
    assert len(segments) == 2
    assert segments[0].start == 0
    assert segments[1].end == 6
