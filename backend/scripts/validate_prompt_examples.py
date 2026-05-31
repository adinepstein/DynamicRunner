from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from jsonschema import RefResolver


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def validate_prompt_examples() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = backend_dir.parent
    schema_dir = repo_root / "shared" / "schemas"
    examples_dir = backend_dir / "prompts" / "examples"

    schemas = {path.name: _load_json(path) for path in schema_dir.glob("*.schema.json")}
    schema_store = {schema["$id"]: schema for schema in schemas.values()}

    fixtures = [
        ("planner.sample.output.json", "plan-output.schema.json"),
        ("adapter.sample.output.json", "adapter-output.schema.json"),
    ]

    for fixture_file, schema_file in fixtures:
        instance = _load_json(examples_dir / fixture_file)
        schema = schemas[schema_file]
        resolver = RefResolver.from_schema(schema, store=schema_store)
        jsonschema.validate(instance=instance, schema=schema, resolver=resolver)
        print(f"OK: {fixture_file} matches {schema_file}")


if __name__ == "__main__":
    validate_prompt_examples()
