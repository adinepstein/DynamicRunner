from dynamicrunner.schema_models import AdapterAgentOutput, PlannerAgentOutput


def test_planner_example_validates_against_generated_model() -> None:
    from pathlib import Path
    import json

    backend_dir = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (backend_dir / "prompts" / "examples" / "planner.sample.output.json").read_text()
    )
    PlannerAgentOutput.model_validate(payload)


def test_adapter_example_validates_against_generated_model() -> None:
    from pathlib import Path
    import json

    backend_dir = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (backend_dir / "prompts" / "examples" / "adapter.sample.output.json").read_text()
    )
    AdapterAgentOutput.model_validate(payload)
