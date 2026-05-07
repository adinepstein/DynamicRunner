# DynamicRunner backend

Python package (`dynamicrunner`) and FastAPI service (Phase 1).

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
```
