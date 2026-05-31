# DynamicRunner backend

Python package (`dynamicrunner`) and FastAPI service (Phase 1).

## Run the API locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set SUPABASE_URL from your Supabase project (Phase 1.4)
uvicorn dynamicrunner.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
```

Or:

```bash
dynamicrunner-api
```

Endpoints:

| Route | Auth | Description |
|---|---|---|
| `GET /healthz` | Public | Liveness check |
| `GET /me` | Bearer JWT | Returns `{ "uid": "<sub>" }` from verified Supabase token |
| `GET /docs` | Public | OpenAPI UI |

Send the Supabase **access token** as `Authorization: Bearer <token>`.

## Regenerate Pydantic models from JSON Schema

JSON Schemas live in [`../shared/schemas/`](../shared/schemas/). After changing any schema:

```bash
cd backend
PIP_INDEX_URL=https://pypi.org/simple python3 -m venv .venv   # once
./scripts/generate_schema_models.sh
```

Requires `datamodel-code-generator` (installed via `pip install -e ".[dev]"`).

Generated code: `src/dynamicrunner/schema_models/` — **do not hand-edit**; fix the schema and re-run the script.

## Tests

```bash
cd backend
. .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
mypy
```
