"""Maps DynamicRunner workout schema → Garmin Connect structured workout payload.

Garmin's structured workout format uses:
- workoutSegments → workoutSteps hierarchy
- stepType: "warmup", "cooldown", "interval", "rest", "repeat"
- endCondition: "time" (seconds) | "distance" (meters) | "lap.button"
- targetType: "heart.rate.zone" | "pace.zone" | "no.target"
"""

from __future__ import annotations

from typing import Any


def map_workout_to_garmin(workout_payload: dict[str, Any]) -> dict[str, Any]:
    """Convert a DynamicRunner workout payload to Garmin Connect structured workout format.

    Args:
        workout_payload: Workout dict matching workout.schema.json

    Returns:
        Garmin-compatible structured workout JSON ready for upload via garth.
    """
    title = workout_payload.get("title", "DynamicRunner Workout")
    description = workout_payload.get("description", "")
    duration_sec = workout_payload.get("estimatedDurationSec", 0)
    structure = workout_payload.get("structure", {})

    garmin_steps: list[dict[str, Any]] = []
    step_order = 1

    # Warmup
    warmup = structure.get("warmup")
    if warmup:
        garmin_step = _map_step(warmup, step_order, step_type="warmup")
        garmin_steps.append(garmin_step)
        step_order += 1

    # Main steps
    main_steps = structure.get("mainSteps", [])
    for step in main_steps:
        if step.get("kind") == "repeat":
            repeat_step, step_order = _map_repeat_block(step, step_order)
            garmin_steps.append(repeat_step)
        else:
            garmin_step = _map_step(step, step_order, step_type="interval")
            garmin_steps.append(garmin_step)
            step_order += 1

    # Cooldown
    cooldown = structure.get("cooldown")
    if cooldown:
        garmin_step = _map_step(cooldown, step_order, step_type="cooldown")
        garmin_steps.append(garmin_step)
        step_order += 1

    # If no structured steps, create a single open step
    if not garmin_steps:
        garmin_steps.append({
            "type": "ExecutableStepDTO",
            "stepOrder": 1,
            "stepType": {"stepTypeId": 3, "stepTypeKey": "interval"},
            "endCondition": _make_end_condition("time", duration_sec),
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
        })

    return {
        "workoutName": title[:50],
        "description": description[:250] if description else None,
        "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
        "estimatedDurationInSecs": duration_sec,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": {"sportTypeId": 1, "sportTypeKey": "running"},
                "workoutSteps": garmin_steps,
            }
        ],
    }


def _map_step(
    step: dict[str, Any], order: int, step_type: str = "interval"
) -> dict[str, Any]:
    """Map a single DynamicRunner Step to a Garmin ExecutableStepDTO."""
    kind = step.get("kind", "duration")

    # End condition
    if kind == "duration":
        end_condition = _make_end_condition("time", step.get("seconds", 600))
    elif kind == "distance":
        end_condition = _make_end_condition("distance", step.get("meters", 1000))
    else:  # lap_button
        end_condition = _make_end_condition("lap.button", 0)

    # Target
    target = step.get("target")
    target_dto = _map_target(target)

    step_type_map = {
        "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup"},
        "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
        "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
        "rest": {"stepTypeId": 4, "stepTypeKey": "rest"},
        "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery"},
    }

    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": step_type_map.get(step_type, step_type_map["interval"]),
        "endCondition": end_condition,
        **target_dto,
    }


def _map_repeat_block(
    block: dict[str, Any], start_order: int
) -> tuple[dict[str, Any], int]:
    """Map a RepeatBlock to a Garmin RepeatGroupDTO."""
    repeat_count = block.get("repeat", 2)
    steps = block.get("steps", [])

    child_steps: list[dict[str, Any]] = []
    child_order = 1

    for i, step in enumerate(steps):
        # Alternate between interval and rest for repeat blocks
        step_type = "interval" if i % 2 == 0 else "recovery"
        garmin_step = _map_step(step, child_order, step_type=step_type)
        child_steps.append(garmin_step)
        child_order += 1

    repeat_dto = {
        "type": "RepeatGroupDTO",
        "stepOrder": start_order,
        "stepType": {"stepTypeId": 6, "stepTypeKey": "repeat"},
        "numberOfIterations": repeat_count,
        "workoutSteps": child_steps,
    }

    return repeat_dto, start_order + 1


def _make_end_condition(condition_type: str, value: int | float) -> dict[str, Any]:
    """Create a Garmin end condition."""
    condition_map = {
        "time": {"conditionTypeId": 2, "conditionTypeKey": "time"},
        "distance": {"conditionTypeId": 3, "conditionTypeKey": "distance"},
        "lap.button": {"conditionTypeId": 1, "conditionTypeKey": "lap.button"},
    }

    result: dict[str, Any] = condition_map.get(
        condition_type,
        {"conditionTypeId": 2, "conditionTypeKey": "time"},
    )

    if condition_type == "time":
        result["conditionValue"] = int(value)
    elif condition_type == "distance":
        result["conditionValue"] = int(value)
    else:
        result["conditionValue"] = None

    return result


def _map_target(target: dict[str, Any] | None) -> dict[str, Any]:
    """Map a DynamicRunner Target to Garmin target fields."""
    if not target:
        return {
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
        }

    kind = target.get("kind")

    if kind == "hrZone":
        zone = target.get("zone", 2)
        return {
            "targetType": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone"},
            "targetValueOne": zone,
            "targetValueTwo": zone,
            "zoneNumber": zone,
        }

    if kind == "pace":
        min_pace = target.get("minSecPerKm", 300)
        max_pace = target.get("maxSecPerKm", 360)
        # Garmin uses m/s for pace targets (inverted: faster = higher m/s)
        min_speed = 1000 / max_pace if max_pace > 0 else 2.5
        max_speed = 1000 / min_pace if min_pace > 0 else 4.0
        return {
            "targetType": {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone"},
            "targetValueOne": round(min_speed, 4),
            "targetValueTwo": round(max_speed, 4),
        }

    if kind == "rpe":
        return {
            "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
        }

    return {
        "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
    }
