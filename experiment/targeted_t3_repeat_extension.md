# Targeted Repeated-Run Validation of the Largest Observed Contrast

## Status and purpose

- Protocol status: frozen before the first extension completion request
- Scientific status: **post-result, budget-constrained, targeted robustness extension**
- Decision date: 2026-07-11
- Motivation: T3 produced the largest observed loss relative to T0 in the
  frozen main matrix, but T3 was absent from the original T0/T2/T4 robustness
  experiment.

This extension tests whether the observed T3--T0 direction is supported across
three new executions on the already fixed 150-issue robustness sample. It is
not preregistered, not a full-test-set rerun, and not an independent replication.
No result from this extension may be used to change the sample, prompt, systems,
parser, estimand, stopping rule, or analysis below.

## Frozen experimental matrix

- Dataset split: official NLBSE 2024 test split.
- Sample: exactly the 150 issue ids used by the original robustness run,
  originally selected with seed 20260704 as 10 issues from each of the 15
  repository-by-gold-label strata. No new selection is performed.
- Sample manifest: `protocol/targeted_t3_repeat_sample.json`; inference loads
  these ids from the label-free test file.
- Conditions: T0 label names only and T3 Markdown-table operational enrichment.
- Systems: `deepseek-v4-flash`, `kimi-k2.7-code`, and `glm-5.2` through the
  existing OpenCode Go adapter only.
- Instruction: canonical P1 only. P2 and P3 are excluded.
- Repeats: three new calls per issue-by-condition-by-system cell.
- Requested generation seeds: repeat 1 = 4409, repeat 2 = 5501, repeat 3 =
  6607. Acceptance of a seed-bearing request does not establish upstream
  deterministic enforcement.
- Canonical task count: 150 x 2 x 3 x 3 = 2,700.

The full task list is shuffled once with Python's frozen deterministic shuffle
and execution seed 20260711. Conditions, systems, and repeats therefore share
the same access period rather than being executed in large condition blocks.
The task-order hash and balance counts are frozen in
`protocol/targeted_t3_repeat_extension_hashes.json`.

## Frozen prompt, parser, and request contract

T0, T3, P1, the system message, user wrapper, issue JSON serialization, and
output schema come unchanged from `protocol/prompt_registry.yaml`. Their frozen
hashes come from `protocol/prompt_hashes.json`. The issue title and body, allowed
labels, exact one-key JSON contract, exact parser, lenient parser, and inference
wrapper are unchanged.

Requested study parameters are temperature 0.0, top-p 1.0, and a legacy visible
output target of 32 tokens. The provider completion cap remains 1,024 because
OpenCode Go routes may count hidden reasoning inside that budget. Temperature
and top-p are sent only on routes that accepted them in the frozen pretest;
Kimi receives provider defaults because its route rejected both fields. The
effective request fields are stored per response. No reasoning, tool, retrieval,
few-shot, or structured-output API mode is requested.

New rows add optional `finish_reason`, returned response model, request id,
full usage object, system fingerprint when exposed, effective request
parameters, invocation id, completion-budget ordinals, and a non-secret
provenance segment. Historical rows are not backfilled or modified.

## Retry, resume, and raw-output policy

- Provider/transport exceptions: at most three attempts in one batch, with the
  existing exponential backoff and 120-second timeout.
- A terminal technical-error checkpoint remains append-only and is pending for
  an explicitly audited resume; successful later rows do not overwrite it.
- A completed empty or malformed assistant response is an experimental output,
  is parsed as invalid as applicable, and is **not** retried.
- Every provider completion attempt, including the three health calls and all
  retry/resume attempts, first reserves one ordinal in the durable revision-wide
  call ledger.

## Completion-call budget

- Planned canonical experiment calls: 2,700.
- Planned provider health calls: 3.
- Default smoke-test calls: 0.
- Retry/smoke reserve after planned calls: 297.
- Hard cap: 3,000 completion attempts across this revision.

The budget guard refuses attempt 3,001. Catalog and limits-page GET requests are
metadata retrieval and do not consume the completion-call ledger. Unused reserve
does not authorize another experiment. No inference wave follows this extension.

## Stop rules

The tmux run stops and writes its current checkpoint/manifest if:

1. any frozen protocol, prompt, parser, provider, sample, or task-order hash
   mismatches;
2. the sample is not exactly the original 150 issue-id set;
3. the planned condition/system/repeat cells are unbalanced;
4. unresolved technical-error tasks exceed 1% of the 2,700 canonical tasks
   (more than 27 tasks);
5. a returned provider model string is explicitly incompatible with the frozen
   system-family rule; or
6. another completion attempt would exceed the 3,000-call cap.

Stopping does not authorize a prompt/model/sample change. Diagnosis and any
resume must use the same frozen task keys; a scientifically different recovery
requires a new reported deviation and cannot exceed the hard cap.

## Frozen estimand and analysis

For repository r, system s, repeat k, and condition c in {T0,T3}, let
F(r,s,k,c) be exact-contract Macro-F1 over the fixed sample issues in repository
r, with invalid exact outputs counted as incorrect predictions. The repeat-level
contrast is

Delta(k) = (1/15) sum over r and s of [F(r,s,k,T3) - F(r,s,k,T0)].

The primary extension estimand is the repeat-averaged contrast

Delta-bar = (1/3) sum over k of Delta(k).

Every repository-by-system cell therefore receives equal weight. Repeats are
reported separately before averaging. The analysis will report:

- all three repeat deltas;
- system-specific and repository-specific repeat-averaged deltas;
- all nine system-by-repeat deltas and their negative-direction count;
- exact invalid rates, lenient-parser deltas, and exact-both-valid conditional
  deltas;
- within-condition pairwise repeat flip rates, unanimous agreement, nominal
  Krippendorff alpha with invalid output as a fourth contract state, and
  prediction stability for T0 and T3; and
- provider response-model, effective-parameter, finish-reason, usage,
  provenance-segment, retry/resume, timing, and task-count audits.

Uncertainty for Delta-bar uses 10,000 draws with analysis seed 20260711. Each
draw keeps the five repositories fixed, resamples issue ids with replacement
inside each repository, and carries every condition-by-system-by-repeat
prediction for a selected issue together. The reported 95% percentile interval
is for this single contrast, so no multiplicity adjustment is applied. The
repeated calls are not treated as independent observations. No additional
post-result subset, prompt, or rescue analysis will be selected after viewing
the extension result.

The comparison table will keep separate:

1. the full 1,500-issue main T3--T0 contrast;
2. the canonical main-P1 T3--T0 contrast on these same 150 issue ids; and
3. each new repeat and Delta-bar.

The first comparison reflects sample composition as well as execution; the new
repeat spread describes repeated execution on the smaller fixed sample. If the
direction is inconsistent, the paper will state that the largest main contrast
did not reproduce consistently on the smaller repeated-run sample. If it is
consistently negative, it will be described only as targeted repeated-run
support, not as full-dataset independent replication.

## Inference scope

The extension interval quantifies issue-composition sensitivity within the five
fixed repositories while jointly retaining the three fixed provider aliases and
three calls. It excludes uncertainty for new repositories, new systems,
provider routing/model drift, future access windows, and a population of
independent generations. Semantic correctness is not adjudicated; all
performance outcomes remain agreement with archived benchmark labels.
