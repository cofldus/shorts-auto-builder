# shorts-auto-builder

스크립트와 에셋 폴더를 입력으로 받아 세로형 쇼츠 영상을 자동 생성하는 도구입니다.

## 기능 요약

- 스크립트 기반 쇼츠 생성 (`start/end/subtitle/narration`)
- 자막(ASS) 생성 및 번인 렌더링
- 배경음악(BGM) 루프, 트림, 내레이션 구간 덕킹
- TTS 내레이션 생성 (`--voice edge`, `--voice piper`, `--voice openai`)
- 이미지 모션 제어 (`--image-motion none|slow`)

## 설치

- Python 3.10+ 권장
- FFmpeg, FFprobe 설치 및 PATH 등록 필요
- `ffmpeg -version`, `ffprobe -version` 명령이 터미널에서 동작해야 함
- PATH 인식이 안 될 경우 WinGet 설치 경로를 자동 탐색하며, 필요 시 `FFMPEG_BIN`, `FFPROBE_BIN` 환경 변수로 직접 지정 가능

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
python -m shorts_maker --script script.txt --assets assets --out output.mp4 --voice none --image-motion none
```

### 최소 실행 예시 2: Edge TTS 사용

```bash
python -m shorts_maker --script script.txt --assets assets --out output.mp4 --voice edge --voice-lang ko-KR --voice-voice ko-KR-SunHiNeural --image-motion none
```

### 최소 실행 예시 3: OpenAI TTS 사용

```bash
set OPENAI_API_KEY=your_api_key
python -m shorts_maker --script script.txt --assets assets --out output.mp4 --voice openai --voice-lang ko-KR --voice-voice alloy --image-motion none
```

### 최소 실행 예시 4: Piper 로컬 TTS 사용

```bash
set PIPER_MODEL=C:\models\ko_KR-voice.onnx
python -m shorts_maker --script script.txt --assets assets --out output.mp4 --voice piper --voice-voice 0 --image-motion none
```

## 데모 에셋 실행

```bash
python -m shorts_maker --script demo_assets\script.txt --assets demo_assets --out output_demo_none.mp4 --voice none --duration 35 --image-motion none
```

```bash
python -m shorts_maker --script demo_assets\script.txt --assets demo_assets --out output_demo_edge.mp4 --voice edge --voice-lang ko-KR --voice-voice ko-KR-SunHiNeural --duration 35 --image-motion none
```

## 옵션 설명

- `--duration` (기본 30): 전체 길이(초)
- `--size` (기본 1080x1920): 출력 해상도
- `--fps` (기본 30): 프레임레이트
- `--bgm`: 배경음악 파일 경로
- `--voice`: `none`, `edge`, `piper`, `openai`
- `--voice-lang`: TTS 언어 코드
- `--voice-voice`: TTS 화자 이름
- `--font`: 자막 폰트 파일 경로
- `--subtitle-pos`: `bottom` 또는 `center`
- `--safe-margin`: 자막 안전 여백 비율 (`0 <= x < 0.5`)
- `--fade`: 장면 전환 페이드 시간(초)
- `--image-motion`: 이미지 모션 (`none`, `slow`)
- `--seed`: 에셋 선택 재현용 시드
- `--verbose`: FFmpeg/FFprobe 실행 로그 출력

## 서비스형 자동화 확장

Vercel 기반 서비스로 확장하려면 `apps/web` 폴더를 사용하세요.

- 사용자 입력: 주제 키워드, 톤, 길이, 첨부 이미지/영상
- 자동 스크립트 생성: 서버 API에서 키워드로 `script.txt` 형식 생성
- 작업 큐 등록: 업로드 파일 메타데이터와 스크립트를 작업 워커로 전달
- 렌더링 워커: Python 엔진(`shorts_maker`)으로 최종 MP4 생성
- 결과 전달: 저장소 URL을 프론트에 반환
- 현재 `apps/web/app/api/jobs`는 워커의 `/render-upload`를 직접 호출합니다.
- 생성형 모드: `apps/web/app/api/creative` -> 워커 `/generate-creative` 호출
- 생성 방식:
  - `mock`: 비용 없이 로컬 생성 자산으로 테스트
  - `openai_image`: 이미지 생성 API 기반 장면 생성

주의:

- Vercel 서버리스 함수에서 FFmpeg 대용량 렌더링을 직접 돌리는 것은 권장하지 않습니다.
- 렌더링은 별도 워커(Cloud Run/Render/Railway 등)로 분리하세요.

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
- `--voice piper` 사용 시 `PIPER_MODEL` 환경 변수(onnx 모델 파일 경로)가 필요합니다.
- `--voice piper`에서 `--voice-voice`는 숫자 화자 ID(예: `0`)로 넣을 수 있습니다.
- `--voice openai` 사용 시 `OPENAI_API_KEY` 환경 변수가 필요합니다.
- 모듈 오류가 나면 의존성을 다시 설치하세요.
- 이미지가 흔들려 보이면 `--image-motion none`으로 실행하세요.

## 생성형 영상 고도화

- 생성형 모드 API: `apps/web/app/api/creative`
- 워커 엔드포인트: `/generate-creative`
- 모드:
  - `mock`: 비용 없는 로컬 테스트
  - `openai_image`: 이미지 생성 기반
  - `external_video`: 외부 영상 생성 provider 연동
  - `runway`: Runway API 기반 생성
- 저장소:
  - `STORAGE_BACKEND=local` 또는 `STORAGE_BACKEND=s3`
  - S3/R2 사용 시 `output_url` 반환 가능

- 추가 모드:
  - `replicate_video`: Replicate 전용 어댑터
- Runway 세부 모드:
  - `text_to_video`
  - `image_to_video` (소스 이미지 필요)
  - `video_to_video` (소스 비디오 필요)
- Runway 환경 변수:
  - `RUNWAY_API_KEY`
  - `RUNWAY_API_BASE` (기본: `https://api.dev.runwayml.com`)
  - `RUNWAY_API_VERSION` (기본: `2024-11-06`)
  - `RUNWAY_TEXT_MODEL`, `RUNWAY_IMAGE_MODEL`, `RUNWAY_VIDEO_MODEL`
- S3 URL 모드:
  - `S3_URL_MODE=public` 또는 `S3_URL_MODE=presigned`
- 상태 조회:
  - 워커 `GET /jobs/{job_id}`
  - 웹 `GET /api/jobs/{jobId}`
