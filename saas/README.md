# saas/ — AIOps Platform Micro-SaaS Scaffold

Phase 1 skeleton wrapping the IaC Generator agent as a production SaaS product.

```
saas/
├── api/          FastAPI backend — POST /runs (SSE), GET /runs/:id, GET /healthz
│   ├── main.py
│   ├── src/
│   │   ├── routers/
│   │   │   ├── runs.py     IaC generation jobs (SSE streaming)
│   │   │   └── health.py   Liveness probe
│   │   └── core/
│   │       ├── auth.py     TODO: Supabase JWT stub
│   │       └── billing.py  TODO: Stripe metered usage stub
│   └── requirements.txt
│
└── web/          Next.js 14 frontend — prompt form + live SSE output viewer
    ├── app/
    │   ├── page.tsx        Home — prompt form + streamed output
    │   └── layout.tsx
    ├── components/
    │   ├── RunForm.tsx     Prompt input + provider selector
    │   └── RunOutput.tsx   Pipeline progress + generated file viewer
    └── lib/
        └── api.ts          startRun() + getRun() client helpers
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Browser (Next.js 14)                                                   │
│                                                                         │
│  RunForm → POST /runs ──────────────────────────────────────────────┐  │
│                                                                      │  │
│  RunOutput ← SSE events ────────────────────────────────────────────┘  │
│     event: node    {"node": "generate", "message": "..."}               │
│     event: file    {"filename": "main.tf", "content": "..."}            │
│     event: done    {"run_id": "...", "file_count": 4}                   │
└─────────────────────────────────────────────────────────────────────────┘
             │ POST /runs (SSE)
             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI  (saas/api/)                                                   │
│                                                                         │
│  POST /runs  ────────────────────────────────────────────────────────┐  │
│    validate request                                                   │  │
│    TODO: require_auth()  ← Supabase JWT                               │  │
│    TODO: billing.record_intent()  ← Stripe                           │  │
│    stream _stream_run() via SSE                                       │  │
│                                                                       │  │
│  GET /runs/{id}  ────────────────────── poll in-memory _runs dict    │  │
│  GET /healthz    ────────────────────── always 200 ok                │  │
└───────────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  IaC Generator Agent  (agents/iac-generator/)                          │
│                                                                         │
│  LangGraph 5-node pipeline:                                            │
│  clarify → plan → generate → validate (terraform validate) → output   │
│                                                                         │
│  Output: Terraform HCL files (providers.tf, main.tf, variables.tf, …) │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1 TODOs (before charging users)

| Area | TODO | File |
|---|---|---|
| Auth | Replace stub with Supabase JWT verification | `saas/api/src/core/auth.py` |
| Billing | Replace stub with Stripe metered usage recording | `saas/api/src/core/billing.py` |
| Storage | Replace in-memory `_runs` dict with PostgreSQL | `saas/api/src/routers/runs.py` |
| Agent | Wire real IaC Generator instead of stub SSE | `saas/api/src/routers/runs.py` → `_stream_run()` |
| Auth (frontend) | Add Supabase `<AuthProvider>` + login gate | `saas/web/app/page.tsx` |
| Credits | Show remaining Stripe credits in header | `saas/web/app/page.tsx` |
| Rate limiting | Add per-user rate limits (slowapi) | `saas/api/main.py` |
| Cancel | Add `DELETE /runs/{id}` endpoint | `saas/api/src/routers/runs.py` |
| Quota | Enforce Stripe credit quota before run starts | `saas/api/src/core/billing.py` |

---

## Quick start

```bash
# Backend
cd saas/api
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8080

# Smoke test
curl http://localhost:8080/healthz
# → {"status":"ok","version":"0.1.0"}

curl -N -X POST http://localhost:8080/runs \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create an AWS VPC with two public subnets", "provider": "aws"}'
# → SSE stream of events...

# Frontend
cd saas/web
npm install  # first time
cp .env.local.example .env.local
npm run dev
# → http://localhost:3000
```
