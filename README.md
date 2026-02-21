# shorts-auto-builder

스크립트와 에셋 폴더를 입력으로 받아 세로형 쇼츠 영상을 자동 생성하는 도구입니다.

## 기능 요약

- 스크립트 기반 쇼츠 생성 (`start/end/subtitle/narration`)
- 자막(ASS) 생성 및 번인 렌더링
- 배경음악(BGM) 루프, 트림, 내레이션 구간 덕킹
- TTS 내레이션 생성 (`--voice edge`)

## 설치

- Python 3.10+ 권장
- FFmpeg, FFprobe 설치 및 PATH 등록 필요
- `ffmpeg -version`, `ffprobe -version` 명령이 터미널에서 동작해야 함

```bash
pip install -r requirements.txt
```

## 빠른 시작

```text
shorts-auto-builder/
  script.txt
  assets/
    clip1.mp4
    clip2.mp4
    img1.jpg
    img2.png
```

스크립트는 빈 줄로 세그먼트를 구분하며 `key: value` 형식을 사용합니다.

- 필수 키: `start`, `end`
- 선택 키: `subtitle`, `narration`

예시:

```txt
start: 0.0
end: 6.0
subtitle: 또 하루가 시작되고
narration: 아침이 오면, 또 시작이죠.

start: 6.0
end: 15.0
subtitle: 괜찮은 척,\n하고 있었죠
narration: 웃으면서 일했지만, 사실은 조금 벅찼죠.
```

### 최소 실행 예시 1: TTS 없이

```bash
python -m shorts_maker --script script.txt --assets assets --out output.mp4 --voice none
```

### 최소 실행 예시 2: Edge TTS 사용

```bash
python -m shorts_maker --script script.txt --assets assets --out output.mp4 --voice edge --voice-lang ko-KR --voice-voice ko-KR-SunHiNeural
```

## 옵션 설명

- `--duration` (기본 30): 전체 길이(초)
- `--size` (기본 1080x1920): 출력 해상도
- `--fps` (기본 30): 프레임레이트
- `--bgm`: 배경음악 파일 경로
- `--voice`: `none` 또는 `edge`
- `--voice-lang`: TTS 언어 코드
- `--voice-voice`: TTS 화자 이름
- `--font`: 자막 폰트 파일 경로
- `--subtitle-pos`: `bottom` 또는 `center`
- `--safe-margin`: 자막 안전 여백 비율 (`0 <= x < 0.5`)
- `--fade`: 장면 전환 페이드 시간(초)
- `--seed`: 에셋 선택 재현용 시드
- `--verbose`: FFmpeg/FFprobe 실행 로그 출력

## 트러블슈팅

### FFmpeg/libass 관련

- 자막 번인에는 FFmpeg `subtitles` 필터(`libass`)가 필요합니다.
- 필터 확인:

```bash
ffmpeg -hide_banner -filters
```

### Windows 경로 이슈

- 경로에 공백/특수문자가 많으면 FFmpeg 필터 인자에서 문제가 날 수 있습니다.
- 가능하면 짧은 작업 경로(예: `C:\work\shorts-auto-builder`)를 사용하세요.

### 폰트 이슈

- 한글 글리프가 깨지면 한글 지원 폰트를 설치하고 `--font`로 직접 지정하세요.

### TTS 이슈

- `--voice edge` 사용 시 네트워크 상태에 따라 생성 속도가 느릴 수 있습니다.
- 모듈 오류가 나면 의존성을 다시 설치하세요.
