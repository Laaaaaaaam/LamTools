# __MEMBER_NAME__

> __MEMBER_NAME__ member of LamTools

## Dev Commands

```bash
cd backend && py -3.14 -m uvicorn app.main:app --reload --port __BACKEND_PORT__
cd frontend && npm run dev
```

## Architecture

- Backend: FastAPI + lamtools_core
- Frontend: Vue3 + @lamtools/ui
- Member package: manifest, kit, prompts, tools, verification
- Runtime, provider parsing, session/event fan-out, and snapshots stay in Core
