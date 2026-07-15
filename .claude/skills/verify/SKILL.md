---
name: verify
description: Exercise the digest through FastAPI and the React UI with isolated source fixtures.
---

# Runtime verification

1. Start the isolated backend from the repository root:

```bash
DATABASE_PATH=/tmp/daily-ai-digest-verify.db \
GITHUB_TOKEN=verify YOUTUBE_API_KEY=verify GEMINI_API_KEY= \
CORS_ALLOW_ORIGINS=http://127.0.0.1:15173 \
PYTHONPATH="$PWD/backend" .venv/bin/python .claude/skills/verify/mock_server.py
```

2. Trigger a digest without sending email and inspect the public API:

```bash
curl -X POST http://127.0.0.1:18080/api/digest/trigger \
  -H 'content-type: application/json' \
  -d '{"digest_type":"daily","send_email":false,"force":true}'
curl http://127.0.0.1:18080/api/digest/today
curl 'http://127.0.0.1:18080/api/digest/history?limit=10'
```

3. Start the frontend and inspect the GitHub, arXiv, YouTube, and history views:

```bash
VITE_API_BASE_URL=http://127.0.0.1:18080/api \
npm --prefix frontend run dev -- --host 127.0.0.1 --port 15173
```

Use a fresh `DATABASE_PATH` when verifying migrations. The fixture server never sends email and does not call external source APIs.
