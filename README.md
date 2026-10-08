# WhatToSell

A product-research tool for cross-border e-commerce sellers. Enter a product keyword, and it collects real discussions from Reddit and TikTok to validate demand, then checks Amazon, TikTok Shop, Temu/AliExpress and 1688 to judge whether there is a supply-side opportunity.

- Design: [docs/DESIGN.md](docs/DESIGN.md)
- Phase plan: [docs/ROADMAP.md](docs/ROADMAP.md)

## Running locally

```bash
cp .env.example .env            # fill in LLM keys etc.
docker compose up -d            # Postgres :55432, Redis :6380

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload     # API at http://localhost:8000/docs
uv run arq app.worker.WorkerSettings     # in another terminal: background job worker
uv run pytest                            # tests (creates the wts_test database automatically)
```

## Code layout

```
backend/app/
  config.py         settings and depth tiers (light / standard / deep)
  models.py         data model
  channels/         channel adapter interface + registry (Reddit/TikTok implementations land in phase 2)
  supply/           supply-side platform adapter interface
  pipeline/         search flow: collect → demand side → supply side
  llm.py            provider-agnostic LLM wrapper: per-task model routing, structured JSON output with validation and retry
  api/              REST endpoints
  worker.py         arq worker
```

To add a data source, implement `ChannelAdapter` (or `SupplyAdapter`) and call `register()`. Nothing upstream needs to change.
