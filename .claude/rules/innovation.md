---
paths:
  - "innovation/**/*"
  - "docs/innovation/**/*"
---

# Innovation Path Rules

- Client code depends only on the versioned Model API Contract through the Model Gateway.
- Mock/synthetic provider is the default and offline backup; provider-native objects remain in adapters.
- Validate temporal/authorization input and provider output before rendering.
- Human review is mandatory; red-flag escalation cannot be silently downgraded.
- External real/linkable patient data, deployment, or publication requires exact human approval.

