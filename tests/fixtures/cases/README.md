# Frozen synthetic evaluation cases

Acceptance criterion A4 requires a frozen case set covering multiple systems, urgency
levels, missingness, contradiction and provider failure.

**These are synthetic cases with author-declared expectations, not clinical ground truth.**
`expected_minimum_urgency` is the floor a conservative system must reach for a case
constructed this way. It is a property of the fixture, decided when the fixture was
written, not a clinical label and not a validated reference standard. No clinical claim
may rest on it.

The set is frozen in the sense that matters: the expectations were written before any
result was measured, so a metric cannot be chosen after seeing which one flatters the
system (`EVALUATION_CONTRACT.md`, `CLAUDE.md` §Research gates).

Changing a case, or its expectation, changes what the numbers mean. Do it in a commit
that says so.
