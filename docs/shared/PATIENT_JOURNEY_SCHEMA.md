# Patient Journey Schema

**Machine schema:** `schemas/patient-journey.schema.json`  
**Version:** 1.0.0  
**Principle:** an append-only timeline whose snapshots expose only time-valid evidence

## Top-level object

| Field | Required | Meaning |
|---|---:|---|
| `schema_version` | yes | semantic contract version |
| `journey_id` | yes | opaque stable journey identifier |
| `patient_id` | yes | opaque stable patient identifier used for splitting |
| `encounter_id` | yes | opaque encounter identifier |
| `split` | yes | patient-level split |
| `data_classification` | yes | classification from Data Contract |
| `source` | yes | dataset/system and version |
| `encounter_start` | yes | ISO-8601 timestamp |
| `events` | yes | ordered evidence/label events |
| `outcomes` | no | later evidence with true availability; never implicit early input |

## Event object

Required:

- `event_id`, unique within journey;
- `event_type`: `CHIEF_COMPLAINT`, `TRIAGE_NOTE`, `DEMOGRAPHICS`, `HISTORY`, `MEDICATION`, `ALLERGY`, `VITAL`, `EXAM`, `LAB`, `ECG`, `IMAGE_2D`, `IMAGE_3D`, `REPORT`, `CONSULT`, `DIAGNOSIS`, `DISPOSITION`, `OUTCOME`, or versioned extension;
- `modality`: `TEXT`, `STRUCTURED`, `IMAGE_2D`, `IMAGE_3D`, `SIGNAL`, `LABEL`, or `REFERENCE`;
- `observed_at` and `available_at_time` in ISO-8601 UTC or offset form;
- `source_ref` with dataset/system/version and safe record reference;
- `status` and `data_classification`;
- exactly one safe `payload_ref`/checksum or inline synthetic `value` permitted by schema/policy.

Optional fields include `recorded_at`, `units`, `code`, `body_site`, image geometry, language, provenance transforms, missingness reason, authorization tags, and quality flags.

## Snapshot operation

Given `decision_time = T`:

1. select events with `available_at_time <= T`;
2. apply authorization and task filters;
3. retain explicit missing/unavailable catalog entries without exposing future values;
4. order by `available_at_time`, then stable event ID;
5. record selected evidence IDs and rejected reasons;
6. never mutate the base journey.

The snapshot records `journey_id`, `decision_time`, task, evidence IDs, missingness, data/split/transform versions, and checksum. A later snapshot is a new artifact.

## Canonical synthetic example

```json
{
  "schema_version": "1.0.0",
  "journey_id": "journey-syn-0001",
  "patient_id": "patient-syn-0001",
  "encounter_id": "encounter-syn-0001",
  "split": "expert_test",
  "data_classification": "SYNTHETIC",
  "source": {"system": "project-fixture", "version": "1.0.0"},
  "encounter_start": "2026-01-01T09:00:00Z",
  "events": [
    {
      "event_id": "ev-001",
      "event_type": "CHIEF_COMPLAINT",
      "modality": "TEXT",
      "observed_at": "2026-01-01T09:00:00Z",
      "available_at_time": "2026-01-01T09:00:00Z",
      "status": "AVAILABLE",
      "data_classification": "SYNTHETIC",
      "source_ref": {"system": "project-fixture", "version": "1.0.0", "record_ref": "syn-0001-cc"},
      "value": "Chest discomfort reported during the simulated intake."
    },
    {
      "event_id": "ev-002",
      "event_type": "VITAL",
      "modality": "STRUCTURED",
      "observed_at": "2026-01-01T09:10:00Z",
      "available_at_time": "2026-01-01T09:12:00Z",
      "status": "AVAILABLE",
      "data_classification": "SYNTHETIC",
      "source_ref": {"system": "project-fixture", "version": "1.0.0", "record_ref": "syn-0001-vital"},
      "value": {"code": "heart_rate", "value": 104, "unit": "beats/min"}
    },
    {
      "event_id": "ev-003",
      "event_type": "DIAGNOSIS",
      "modality": "LABEL",
      "observed_at": "2026-01-01T12:00:00Z",
      "available_at_time": "2026-01-01T13:00:00Z",
      "status": "AVAILABLE",
      "data_classification": "SYNTHETIC",
      "source_ref": {"system": "project-fixture", "version": "1.0.0", "record_ref": "syn-0001-final"},
      "value": {"category": "synthetic-final-label"}
    }
  ]
}
```

At `09:15Z`, `ev-001` and `ev-002` are available; `ev-003` is forbidden even if stored in the same file.

## Validation and evolution

Schema validation does not prove temporal validity; run `scripts/temporal_leakage_audit.py`. Breaking field/semantic changes increment the major version and require migration fixtures. New optional fields increment minor version. Fixes that do not alter accepted data increment patch version.

