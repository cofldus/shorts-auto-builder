# 워커 실행 가이드

```bash
pip install -r worker/requirements.txt
uvicorn worker.main:app --host 0.0.0.0 --port 8000
```

## 상태 조회

```bash
curl http://localhost:8000/health
curl http://localhost:8000/jobs/{job_id}
```

## 생성형 렌더

```bash
curl -X POST http://localhost:8000/generate-creative \
  -H "Content-Type: application/json" \
  -d "{\"topic\":\"직장인 위로\",\"tone\":\"따뜻하고 진정성 있게\",\"duration\":30,\"style\":\"cinematic vertical short\",\"voice\":\"edge\",\"image_motion\":\"slow\",\"generation_mode\":\"mock\"}"
```

## external_video provider

```bash
set VIDEO_PROVIDER_API_BASE=https://provider.example.com
set VIDEO_PROVIDER_API_KEY=your_key
set VIDEO_PROVIDER_CREATE_PATH=/v1/video/jobs
set VIDEO_PROVIDER_STATUS_PATH=/v1/video/jobs/{job_id}
set VIDEO_PROVIDER_POLL_SEC=2
set VIDEO_PROVIDER_POLL_MAX=45
```

## replicate_video provider

```bash
set REPLICATE_API_TOKEN=your_token
set REPLICATE_MODEL=kwaivgi/kling-v1.6-pro
set REPLICATE_VERSION=
set REPLICATE_POLL_SEC=2
set REPLICATE_POLL_MAX=60
```

## 저장소 업로드(S3/R2)

```bash
set STORAGE_BACKEND=s3
set S3_BUCKET=your-bucket
set S3_REGION=ap-northeast-2
set S3_ENDPOINT_URL=
set S3_PREFIX=shorts
set S3_PUBLIC_BASE_URL=https://cdn.example.com
set S3_URL_MODE=public
set S3_PRESIGNED_EXPIRES=3600
```

- `S3_URL_MODE=public`: 일반 공개 URL 반환
- `S3_URL_MODE=presigned`: 유효기간 URL 반환
