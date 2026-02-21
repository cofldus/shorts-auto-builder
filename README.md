# shorts-auto-builder

FFmpeg 기반으로 스크립트(`script.txt`)와 에셋 폴더를 조합해 세로형 쇼츠 영상을 자동 생성하는 도구입니다.

## 프로젝트 소개
- 텍스트 스크립트의 시간 구간(`start`, `end`)을 기준으로 장면을 구성합니다.
- 자막(ASS), 배경음악(BGM), 선택적 음성 합성(TTS)을 한 번에 렌더링합니다.
- 동일 입력에 대해 `--seed` 값으로 결정론적 결과를 재현할 수 있습니다.

## 기능 요약
- 스크립트 기반 타임라인 생성 (`start`, `end`, `subtitle`, `narration`)
- 비디오 우선 에셋 선택 + 이미지 Ken Burns 효과 자동 적용
- 9:16(기본 1080x1920) 크롭/리사이즈 및 세그먼트 연결
- ASS 자막 버닝 (`libass` 필요), 안전 여백/위치 옵션 지원
- BGM 루프/트림 및 내레이션 구간 덕킹
- Edge TTS 기반 한국어 내레이션 생성(선택)

## 설치
### 1) Python 의존성
- Python 3.10 이상 권장
- 기본 실행은 표준 라이브러리 중심이며, `--voice edge` 사용 시 `requirements.txt` 설치가 필요합니다.

```bash
pip install -r requirements.txt
```

### 2) FFmpeg / FFprobe 설치
- `ffmpeg`, `ffprobe` 실행 파일이 PATH에 있어야 합니다.
- 자막 렌더링을 위해 FFmpeg에 `subtitles` 필터(`libass`)가 포함되어야 합니다.

확인 명령:
```bash
ffmpeg -hide_banner -version
ffprobe -hide_banner -version
ffmpeg -hide_banner -filters | grep subtitles
```

## 빠른 시작
### 1) 폴더 구조 준비
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

### 2) 예제 스크립트 준비
- 예제 파일: `examples/직장인_위로_30초.txt`
- 필요 시 내용을 `script.txt`로 복사해 사용하세요.

### 3) 최소 실행 예시 1 (TTS 없이)
```bash
python -m shorts_maker \
  --script examples/직장인_위로_30초.txt \
  --assets assets \
  --out output_no_tts.mp4 \
  --duration 30 \
  --voice none \
  --bgm audio/bgm.mp3 \
  --subtitle-pos bottom \
  --safe-margin 0.08 \
  --seed 42
```

### 4) 최소 실행 예시 2 (Edge TTS 사용)
```bash
python -m shorts_maker \
  --script examples/직장인_위로_30초.txt \
  --assets assets \
  --out output_tts.mp4 \
  --duration 30 \
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

## 주요 옵션
- `--script`: 스크립트 파일 경로
- `--assets`: 에셋 폴더 경로(하위 폴더 재귀 탐색)
- `--out`: 출력 mp4 경로
- `--duration`: 총 길이(초), 기본 30
- `--size`: 출력 해상도, 기본 `1080x1920`
- `--fps`: 프레임레이트, 기본 30
- `--bgm`: 배경음악 파일 경로(선택)
- `--voice`: `none` 또는 `edge`
- `--voice-lang`: TTS 언어(기본 `ko-KR`)
- `--voice-voice`: TTS 보이스(기본 `ko-KR-SunHiNeural`)
- `--font`: 자막 폰트 경로(선택)
- `--subtitle-pos`: `bottom` 또는 `center`
- `--safe-margin`: 자막 안전 여백 비율
- `--fade`: 세그먼트 전환 페이드 시간
- `--seed`: 에셋 선택 시드
- `--verbose`: ffmpeg/ffprobe 실행 명령 출력

## 트러블슈팅
### 1) Windows 경로 관련 오류
- 경로에 공백이 있으면 따옴표를 사용해 감싸세요.
- PowerShell/명령 프롬프트에서 역슬래시 이스케이프가 달라질 수 있으니, 가능하면 짧은 영문 경로를 사용하세요.
- 자막 필터 경로 오류가 나면 `--script`, `--assets`, `--font` 경로에 특수문자가 없는지 확인하세요.

### 2) libass/subtitles 필터 오류
- `FFmpeg subtitles filter is unavailable` 오류가 나면, `libass`가 포함된 FFmpeg 빌드를 설치하세요.
- 확인:
  ```bash
  ffmpeg -hide_banner -filters | grep subtitles
  ```

### 3) 폰트/한글 자막 깨짐
- 시스템 기본 폰트에 한글 글리프가 부족하면 자막이 깨질 수 있습니다.
- 한글 지원 폰트를 설치하고 `--font`로 명시하세요.

### 4) Edge TTS 동작 실패
- `--voice edge` 사용 시 `pip install -r requirements.txt`를 먼저 실행하세요.
- 네트워크 환경에 따라 TTS 생성 시간이 길어질 수 있습니다.

## 종료 동작
- 입력 검증 실패 또는 렌더 실패 시 `python -m shorts_maker`는 0이 아닌 종료 코드를 반환합니다.
- 문제 분석이 필요하면 `--verbose` 옵션으로 실행 명령 로그를 확인하세요.

## 브랜치 운영
- 기본 브랜치는 `main`입니다.
- 작업은 `pr/one-shot` 브랜치에서 단일 PR로 통합해 진행합니다.
