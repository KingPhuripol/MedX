# g2 notes: RF-NEWS-AGG5 (rf-1.2.0)

- Rule follows published RCP NEWS2 (2017), SpO2 Scale 1, not the S1r gold (data_factory RF-NEWS-AGG5, NEWS 2012). Disagreements kept, not fixed: new confusion scores 3 here and 0 in gold; supplemental oxygen scores 2 here (gold also 2 when present, but a null oxygen is missing here and 0 in gold); gold scores any null parameter 0, this rule abstains.
- `vital.on_oxygen` is a new S4 fact kind (bool), mapped from Vitals.on_oxygen; null gives no fact.
- Frozen e1 tests that fail by design: `eval/adapters/tests/test_e1_mapping.py::test_mapping_complete` (frozen mapping v1 is pinned to rf-1.1.0, 16 rules; rf-1.2.0 adds the 17th) and `eval/adapters/tests/test_e1_adapters.py::test_triage_hand_case` (hand case H2, SpO2 88 + confusion, now also fires RF-NEWS-AGG5). Editing either would change the frozen e1 adapters hash.
- `slices/s4/eval/metrics_v1.json` pins rf-1.1.0 by design (historical s4 report); no test requires an update.
- i2 scoring maps S1r RF-NEWS-AGG5 to the S4 rule through `eval_i2.score.AGG5_OVERLAY`; e1_mapping_v1.json is untouched.
