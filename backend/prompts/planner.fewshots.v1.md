# Planner — Few-shot examples v1

These exemplars are appended to the Planner system prompt. They demonstrate the *style* of `methodologyRationale` and a few representative workout structures. They are **not** complete plans (full plans are 100+ workouts) — only the parts most useful for calibration.

The runtime injects these examples after the system prompt and before the user's request.

---

## Example 1 — Methodology rationale, beginner-intermediate marathoner

**Athlete summary:**
- Age 34, female, 58 kg
- VO2max 47, last-12w avg weekly mileage 38 km, longest recent run 18 km
- Easy/hard split last 90 d: 68% / 32% (too much intensity)
- Garmin marathon predictor: 3:48
- Goal: 3:35 marathon in 16 weeks

**Methodology:** `polarized_80_20`

**Rationale (model output):**

> Your last 12 weeks averaged 38 km/wk with a 68/32 easy-hard split — that's measurably more intensity than the evidence supports for marathon prep. We're shifting you to an 80/20 polarized model: 4 easy/long days, 1 hard quality session per week through base, adding a second quality session in the build phase. Goal pace 5:05/km is 6% faster than your current Garmin predictor (3:48), which is achievable with 4 months of disciplined easy mileage and one weekly threshold workout. We'll cap weekly volume at 65 km in peak week 13.

---

## Example 2 — Workout structure, threshold session

**Workout:** "4 x 8 min @ threshold, 2 min recovery"

**Structure (model output, JSON):**

```json
{
  "scheduledDate": "2026-06-09",
  "type": "threshold",
  "title": "4 x 8 min @ threshold",
  "estimatedDurationSec": 4200,
  "structure": {
    "warmup": {
      "kind": "duration",
      "seconds": 900,
      "target": { "kind": "hrZone", "zone": 2 }
    },
    "mainSteps": [
      {
        "kind": "repeat",
        "repeat": 4,
        "steps": [
          {
            "kind": "duration",
            "seconds": 480,
            "target": { "kind": "pace", "minSecPerKm": 248, "maxSecPerKm": 258 }
          },
          {
            "kind": "duration",
            "seconds": 120,
            "target": { "kind": "hrZone", "zone": 1 }
          }
        ]
      }
    ],
    "cooldown": {
      "kind": "duration",
      "seconds": 600,
      "target": { "kind": "hrZone", "zone": 1 }
    }
  },
  "targets": { "rpeRange": [7, 8] }
}
```

---

## Example 3 — Workout structure, marathon-pace long run

**Workout:** "24 km long run with 2 x 5 km @ marathon pace"

**Structure (model output, JSON):**

```json
{
  "scheduledDate": "2026-07-04",
  "type": "long",
  "title": "24 km long w/ 2x5km MP",
  "estimatedDurationSec": 8400,
  "structure": {
    "warmup": {
      "kind": "distance",
      "meters": 4000,
      "target": { "kind": "hrZone", "zone": 2 }
    },
    "mainSteps": [
      {
        "kind": "repeat",
        "repeat": 2,
        "steps": [
          {
            "kind": "distance",
            "meters": 5000,
            "target": { "kind": "pace", "minSecPerKm": 305, "maxSecPerKm": 315 }
          },
          {
            "kind": "distance",
            "meters": 2000,
            "target": { "kind": "hrZone", "zone": 2 }
          }
        ]
      }
    ],
    "cooldown": {
      "kind": "distance",
      "meters": 6000,
      "target": { "kind": "hrZone", "zone": 2 }
    }
  },
  "targets": { "rpeRange": [6, 8] }
}
```

---

## Example 4 — Easy/recovery run

**Workout:** "Easy 45 min, conversational"

**Structure:**

```json
{
  "scheduledDate": "2026-06-10",
  "type": "easy",
  "title": "Easy 45 min",
  "estimatedDurationSec": 2700,
  "structure": {
    "mainSteps": [
      {
        "kind": "duration",
        "seconds": 2700,
        "target": { "kind": "hrZone", "zone": 2 },
        "note": "Conversational pace. If you can't speak full sentences, slow down."
      }
    ]
  },
  "targets": { "rpeRange": [3, 5] }
}
```

---

## Example 5 — Rest day

**Structure:**

```json
{
  "scheduledDate": "2026-06-08",
  "type": "rest",
  "title": "Rest",
  "estimatedDurationSec": 0,
  "structure": { "mainSteps": [] }
}
```

(Rest days are required in the output for every non-training calendar day. Their `mainSteps` array is empty and they are not pushed to Garmin.)
