# Missing-Task Recovery for the Targeted T0--T3 Repeat Extension

## Status

- Amendment date: 2026-07-12.
- Scientific status: **post-result, budget-constrained, targeted robustness
  extension recovery**.
- Authorization: the author explicitly authorized the new calls needed to
  minimize submission-rejection risk on 2026-07-12.
- Result-access status at freeze: no targeted prediction has been joined to a
  benchmark label and no partial targeted performance, agreement, stability,
  or direction result has been computed.

This amendment recovers the originally frozen 2,700-task extension; it is not a
new experiment. The original sample, T0/T3 conditions, P1 instruction, systems,
three requested seeds, task order, parser, output contract, estimand, and
analysis plan remain unchanged.

## Reason for recovery

The first execution was stopped at 1,640 successful canonical tasks after a
pre-result code audit found that the OpenAI-compatible SDK retained two
unmetered internal retries. The 1,646 project-ledger reservations therefore did
not prove the intended 3,000-outbound-attempt ceiling. The exact historical
attempt count is not reconstructible; its conservative mechanical range is
1,643--4,938.

The stopped checkpoint is preserved byte-for-byte. Recovery schedules only the
1,060 task keys without a successful record. No completed task is repeated and
no task is selected by prediction content or performance.

## Frozen recovery execution

- Historical successful tasks: 1,640.
- Missing frozen tasks: 1,060.
- Historical checkpoint:
  `results/raw_predictions/targeted-t3-repeat-663908ad29783a37.jsonl`.
- Recovery output: a new append-only JSONL/Parquet checkpoint with a distinct
  run id and provenance segment.
- Queue order: the original deterministic 2,700-task order after filtering out
  successful historical/current recovery keys. Conditions, systems, and
  repeats remain interleaved.
- Concurrency: global 6; DeepSeek 4, Kimi 2, GLM 2.
- Project retry policy: at most three explicitly metered attempts per missing
  task; completed empty or malformed responses are observations and are not
  retried.
- SDK retry policy: `max_retries=0`.
- Timeout: 120 seconds.
- Routes: the same three OpenCode Go aliases only. A fresh immutable catalog
  snapshot and one health call per route precede recovery inference.

## Conservative call budget

The new recovery ledger has a hard cap of 1,360 provider calls:

| Component | Attempts |
|---|---:|
| Missing canonical tasks | 1,060 |
| Route-health calls | 3 |
| Explicit retry reserve | 297 |
| **Recovery hard cap** | **1,360** |

With SDK retries disabled, one recovery-ledger reservation can produce at most
one provider HTTP attempt. A crash between reservation and transmission can
only overcount. Adding the 1,360 recovery cap to the stopped segment's 4,938
mechanical upper bound gives a conservative revision-wide hard cap of 6,298
outbound completion attempts. Unused reserve cannot authorize another
experiment.

## Stop rules

Recovery stops before result access if:

1. any protocol, prompt, sample, original task-order, stopped-checkpoint, code,
   provider-catalog, or recovery hash mismatches;
2. the label-free reconciliation is not exactly 1,640 successful plus 1,060
   missing task keys from the original 2,700-task plan;
3. any previously successful task would be resubmitted;
4. a response model is incompatible with its frozen alias family;
5. unresolved technical-error task keys exceed 27;
6. another call would require recovery-ledger ordinal 1,361; or
7. the union of historical and recovery records is not exactly the original
   balanced 2,700-task matrix.

The run may be resumed after an operational interruption only with the same
configuration and pending task keys. No prompt, sample, condition, system,
repeat, seed, parser, metric, or subset may change.

## Analysis and interpretation

The estimand and 10,000-draw fixed-repository paired issue bootstrap remain
exactly those in `protocol/targeted_t3_repeat_extension.md`. Before the first
targeted benchmark-label join, the complete union of historical and recovery
raw records, manifests, ledgers, preflights, reports, and canonical label-free
Parquet file must be frozen by hash.

The access-window split will be reported as provenance, not treated as a new
factor. If the T3--T0 direction is inconsistent, that result will be stated
without a rescue subset. If it is consistently negative, it will be described
only as targeted repeated-run support on the fixed 150-issue sample, not as
full-dataset independent replication.
