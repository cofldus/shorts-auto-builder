# 워커 실행 가이드

```bash
pip install -r worker/requirements.txt
uvicorn worker.main:app --host 0.0.0.0 --port 8000
```

## 상태 확인

```bash
curl http://localhost:8000/health
```

## 첨부 편집 렌더

```bash
curl -X POST http://localhost:8000/render-upload \
  -F "script_text=$(cat demo_assets/script.txt)" \
  -F "voice=edge" \
  -F "duration=35" \
  -F "image_motion=none" \
  -F "media=@demo_assets/sample1.jpg" \
  -F "media=@demo_assets/sample2.jpg"
```

## 생성형 렌더(무에서 유)

`generation_mode=mock`은 비용 없이 로컬 추상 장면으로 생성합니다.

```bash
curl -X POST http://localhost:8000/generate-creative \
  -H "Content-Type: application/json" \
  -d "{\"topic\":\"직장인 위로\",\"tone\":\"따뜻하고 진정성 있게\",\"duration\":30,\"style\":\"cinematic vertical short\",\"voice\":\"edge\",\"image_motion\":\"slow\",\"generation_mode\":\"mock\"}"
```

`generation_mode=openai_image`은 이미지 생성 API를 사용합니다.

## 환경 변수

```bash
set WORKER_OUTPUT_DIR=worker_outputs
set FFMPEG_BIN=C:\path\to\ffmpeg.exe
set OPENAI_API_KEY=
set OPENAI_IMAGE_MODEL=gpt-image-1
```

## Piper 사용 시 환경 변수

```bash
set PIPER_BIN=piper
set PIPER_MODEL=C:\models\ko_KR-voice.onnx
set PIPER_CONFIG=C:\models\ko_KR-voice.onnx.json
set PIPER_SPEAKER=0
```
