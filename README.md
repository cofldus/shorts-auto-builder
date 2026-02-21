# shorts-auto-builder

Template-based shorts generator for vertical videos using FFmpeg subprocess calls.

## Features

- Script-driven timeline (`script.txt`) with `start/end/subtitle/narration` blocks.
- Deterministic asset selection (`--seed`) with nested `assets/` support.
- Video-first asset policy (falls back to images with Ken Burns zoom).
- ASS subtitle burn-in (`libass`) with safe-margin placement and simple emphasis (`{...}`).
- Optional Edge TTS narration (`--voice edge`) with timeline alignment and duration fitting.
- Optional BGM loop/trim and ducking during narration windows.

## Recommended folder layout

```text
project/
  script.txt
  assets/
    videos/
      clip1.mp4
      clip2.mov
    images/
      still1.jpg
      still2.png
  audio/
    bgm.mp3
```

## Quickstart

### 1) Prerequisites

- Python 3.10+
- FFmpeg + FFprobe in PATH
- FFmpeg built with `libass` (`subtitles` filter)

Install Python dependency (only needed for `--voice edge`):

```bash
pip install -r requirements.txt
```

### 2) Example script: “직장인 위로 30초”

```txt
start: 00:00
end: 00:10
subtitle: 오늘도 수고한 당신, {정말 잘하고 있어요}.
narration: 오늘도 수고한 당신, 정말 잘하고 있어요.

start: 00:10
end: 00:20
subtitle: 잠깐 숨을 고르고, 어깨에 힘을 풀어봐요.
narration: 잠깐 숨을 고르고, 어깨에 힘을 풀어봐요.

start: 00:20
end: 00:30
subtitle: 내일은 더 괜찮아질 거예요. {당신을 응원합니다}.
narration: 내일은 더 괜찮아질 거예요. 당신을 응원합니다.
```

### 3) Run (fully voiced)

```bash
python -m shorts_maker \
  --script script.txt \
  --assets assets \
  --out output.mp4 \
  --duration 30 \
  --size 1080x1920 \
  --fps 30 \
  --voice edge \
  --voice-lang ko-KR \
  --voice-voice ko-KR-SunHiNeural \
  --bgm audio/bgm.mp3 \
  --subtitle-pos bottom \
  --safe-margin 0.08 \
  --fade 0.25 \
  --seed 42 \
  --verbose
```

### 4) Run (no narration)

```bash
python -m shorts_maker --script script.txt --assets assets --out output.mp4 --voice none
```

## Troubleshooting

- **`Required executable not found in PATH: ffmpeg` / `ffprobe`**
  - Install FFmpeg and ensure both executables are available in PATH.

- **`FFmpeg subtitles filter is unavailable`**
  - Your FFmpeg build likely lacks `libass`.
  - Verify with: `ffmpeg -hide_banner -filters` and check `subtitles` exists.

- **Font rendering differences**
  - ASS currently uses system `Arial` default style.
  - If glyph coverage is poor for Korean on your system, install a Korean-capable font.

- **Windows subtitle path errors**
  - This project escapes subtitle paths for FFmpeg filter usage.
  - Prefer normal paths (avoid unusual quoting in shell wrappers).

- **`--voice edge` fails with missing module**
  - Install dependency: `pip install -r requirements.txt`.

## Exit behavior

- `python -m shorts_maker` exits non-zero on validation/render failure.
- Use `--verbose` to print exact FFmpeg/ffprobe commands for debugging.

## 브랜치별 PR 재작성 가이드
- 모든 브랜치의 PR을 다시 올려야 할 때는 아래 보조 스크립트로 브랜치별 한글 템플릿을 출력할 수 있습니다.
- 실제 PR 생성/회수는 GitHub UI 또는 사내 표준 도구로 진행하세요.

```bash
bash scripts/recreate_pr_per_branch.sh
```
