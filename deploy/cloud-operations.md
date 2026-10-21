# Cloud lifecycle diagnostics

The server keeps `/health` as a dependency-free liveness check and `/health/ready` as a coarse
database readiness check. Neither claims that billing, coverage collection, notification delivery
or retention work is progressing.

Cloud operators can optionally configure two independent credentials:

- `SOTTO_CLOUD_OPERATIONS_METRICS_TOKEN` enables `GET /ops/cloud/metrics` and the bounded
  `GET /ops/cloud/coverage-rejections` inspection route. The response is protected, marked
  `Cache-Control: no-store`, and contains fixed lifecycle states, counts, ages, retry attempts,
  recent invoice-to-coverage publication latency, Stripe reconciliation watermark and unresolved
  event ages, feature states (`enabled`, `disabled` or `unconfigured`) and opaque rejection
  fingerprints. It does not include customer, organisation, invoice, subscription, project,
  contact or provider error identifiers.
- `SOTTO_CLOUD_COVERAGE_REPAIR_TOKEN` enables
  `POST /ops/cloud/coverage-rejections/{fingerprint}/repair`. This credential is separate because
  repair performs a bounded authenticated Stripe event read and re-runs the server's existing
  evidence checks. Operators cannot supply or edit payment evidence through this route.

Leave both unset unless an authenticated scraper and the private repair procedure are ready. Do
not reuse credentials for billing review, notice management, retention inspection or purge. The
repair action's `operator_label` is declared attribution under a shared bearer credential, not
proof of the caller's personal identity. Each rejection has a short repair lease and a per-item
cooldown, and each outcome is retained in an audit table.

Metrics are durable-state snapshots, not worker heartbeats. An enabled worker with old due work
needs investigation; if its queue is empty, these metrics alone cannot prove that the worker is
running. A disabled optional worker is not itself a failure. Alert thresholds, delivery
suppression, recovery timing and worker liveness monitoring must be measured and rehearsed in
staging before an operator treats them as tuned. This endpoint is not a paid-lifecycle acceptance
signal. Use the
separate provider sandbox rehearsal for payment-to-access evidence, and use ordinary human and
machine authentication for ciphertext retrieval checks. `scripts/status-probe` checks both when
configured: the machine canary uses `SOTTO_CANARY_TOKEN`; the human canary uses a standard
`st_` session in `SOTTO_HUMAN_CANARY_TOKEN` plus the synthetic environment id in
`SOTTO_HUMAN_CANARY_ENVIRONMENT_ID`. The human account must be dedicated to the canary and have
access only to synthetic ciphertext. Its session expires and must be rotated like any other user
session. Both probes publish only a fixed outcome and never retain the environment id, token,
ciphertext or wrapped keys. Leave the human canary unconfigured until that isolated account exists.

These retrieval checks show that the normal authenticated APIs return ciphertext and grants; they
do not prove a user can decrypt it or that Stripe settled an invoice. The status system cannot
decrypt customer data and does not create grants, billing awards or charges.
