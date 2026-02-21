from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random

from .utils import ValidationError, ensure_path_exists

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


@dataclass(frozen=True)
class AssetPools:
    videos: list[Path]
    images: list[Path]



def scan_assets(assets_dir: str | Path) -> AssetPools:
    root = Path(assets_dir)
    ensure_path_exists(root, "assets directory")
    if not root.is_dir():
        raise ValidationError(f"Assets path is not a directory: {root}")

    videos: list[Path] = []
    images: list[Path] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        suffix = path.suffix.lower()
        if suffix in VIDEO_EXTS:
            videos.append(path)
        elif suffix in IMAGE_EXTS:
            images.append(path)

    if not videos and not images:
        raise ValidationError(f"No supported assets found in directory: {root}")

    return AssetPools(videos=videos, images=images)


def _pick_from_pool(pool: list[Path], rng: random.Random, previous: Path | None) -> Path:
    if not pool:
        raise ValidationError("Asset pool is unexpectedly empty")
    if len(pool) == 1:
        return pool[0]
    candidates = [p for p in pool if p != previous]
    if not candidates:
        candidates = pool
    return candidates[rng.randrange(len(candidates))]


def select_assets_for_segments(
    pools: AssetPools,
    segment_count: int,
    seed: int,
) -> list[Path]:
    rng = random.Random(seed)
    selected: list[Path] = []
    previous: Path | None = None

    preferred = pools.videos if pools.videos else pools.images
    fallback = pools.images if pools.videos else pools.videos

    for _ in range(segment_count):
        pool = preferred or fallback
        choice = _pick_from_pool(pool, rng, previous)
        selected.append(choice)
        previous = choice
    return selected


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS
