# Error-rate review

## When it applies

Use this review when the observed server-error ratio rises above its normal baseline.

## Checks

Compare error counts with total requests and separate the affected route from the service-wide rate.

## When not to use

Do not use this review when request telemetry is missing or the observation window is incomplete.

## Mistake to avoid

Avoid comparing raw error counts across periods with different traffic volumes.
