# 워커 실행 가이드

```bash
pip install -r worker/requirements.txt
uvicorn worker.main:app --host 0.0.0.0 --port 8000
```

요청 예시:

```bash
curl -X POST http://localhost:8000/render \
  -H "Content-Type: application/json" \
  -d "{\"script_path\":\"demo_assets/script.txt\",\"assets_path\":\"demo_assets\",\"output_path\":\"worker_output.mp4\",\"voice\":\"edge\",\"duration\":35}"
```
