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

## 생성형 렌더

```bash
curl -X POST http://localhost:8000/generate-creative \
  -H "Content-Type: application/json" \
  -d "{\"topic\":\"직장인 위로\",\"tone\":\"따뜻하고 진정성 있게\",\"duration\":30,\"style\":\"cinematic vertical short\",\"voice\":\"edge\",\"image_motion\":\"slow\",\"generation_mode\":\"mock\"}"
```

## external_video provider 환경 변수

```bash
set VIDEO_PROVIDER_API_BASE=https://provider.example.com
set VIDEO_PROVIDER_API_KEY=your_key
set VIDEO_PROVIDER_CREATE_PATH=/v1/video/jobs
set VIDEO_PROVIDER_STATUS_PATH=/v1/video/jobs/{job_id}
set VIDEO_PROVIDER_POLL_SEC=2
set VIDEO_PROVIDER_POLL_MAX=45
```

## 저장소 업로드(S3/R2)

```bash
set STORAGE_BACKEND=s3
set S3_BUCKET=your-bucket
set S3_REGION=ap-northeast-2
set S3_ENDPOINT_URL=
set S3_PREFIX=shorts
set S3_PUBLIC_BASE_URL=https://cdn.example.com
```

`STORAGE_BACKEND=local`이면 로컬 경로를 반환하고, `WORKER_PUBLIC_BASE_URL`이 있으면 공개 URL도 함께 반환합니다.

## Piper 사용 시 환경 변수

```bash
set PIPER_BIN=piper
set PIPER_MODEL=C:\models\ko_KR-voice.onnx
set PIPER_CONFIG=C:\models\ko_KR-voice.onnx.json
set PIPER_SPEAKER=0
```
