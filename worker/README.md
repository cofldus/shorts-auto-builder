# 워커 실행 가이드

```bash
pip install -r worker/requirements.txt
uvicorn worker.main:app --host 0.0.0.0 --port 8000
```

## 상태 확인

```bash
curl http://localhost:8000/health
```

## 로컬 경로 기반 렌더

```bash
curl -X POST http://localhost:8000/render \
  -H "Content-Type: application/json" \
  -d "{\"script_path\":\"demo_assets/script.txt\",\"assets_path\":\"demo_assets\",\"output_path\":\"worker_output.mp4\",\"voice\":\"edge\",\"duration\":35}"
```

## 파일 업로드 기반 렌더

```bash
curl -X POST http://localhost:8000/render-upload \
  -F "script_text=$(cat demo_assets/script.txt)" \
  -F "voice=edge" \
  -F "duration=35" \
  -F "image_motion=none" \
  -F "media=@demo_assets/sample1.jpg" \
  -F "media=@demo_assets/sample2.jpg"
```

## Piper 사용 시 환경 변수

```bash
set PIPER_BIN=piper
set PIPER_MODEL=C:\models\ko_KR-voice.onnx
set PIPER_CONFIG=C:\models\ko_KR-voice.onnx.json
set PIPER_SPEAKER=0
```
