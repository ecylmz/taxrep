# Supplementary Material S1: Audit and Sensitivity Tables

## S1.1 Execution-Order Audit

Main inference used `execution_order: deterministic_shuffle` with seed 20260704. The planned task-index p10, median, and p90 values in Table @tab:s1-run-order show that every taxonomy condition appeared across the beginning, middle, and end of each system run rather than as one contiguous condition block.

Table: Main-inference execution-order audit. {#tab:s1-run-order}

| System | Prompt | First UTC | Last UTC | Requests | Idx p10 | Idx med. | Idx p90 |
|---|---|---|---|---|---|---|---|
| DeepSeek | Label-only | 2026-07-05 05:33 | 2026-07-06 07:08 | 1500 | 711 | 3701 | 6843 |
| DeepSeek | Compact-prose enrichment | 2026-07-05 05:33 | 2026-07-06 07:08 | 1500 | 706 | 3722 | 6661 |
| DeepSeek | Bullet-list enrichment | 2026-07-05 05:33 | 2026-07-06 07:08 | 1500 | 801 | 3760 | 6759 |
| DeepSeek | Markdown-table enrichment | 2026-07-05 05:33 | 2026-07-06 07:08 | 1500 | 786 | 3824 | 6713 |
| DeepSeek | JSON-like-schema enrichment | 2026-07-05 05:33 | 2026-07-06 07:08 | 1500 | 756 | 3740 | 6770 |
| GLM | Label-only | 2026-07-06 13:32 | 2026-07-07 09:26 | 1500 | 711 | 3701 | 6843 |
| GLM | Compact-prose enrichment | 2026-07-06 13:32 | 2026-07-07 09:26 | 1500 | 706 | 3722 | 6661 |
| GLM | Bullet-list enrichment | 2026-07-06 13:31 | 2026-07-07 09:26 | 1500 | 801 | 3760 | 6759 |
| GLM | Markdown-table enrichment | 2026-07-06 13:32 | 2026-07-07 09:26 | 1500 | 786 | 3824 | 6713 |
| GLM | JSON-like-schema enrichment | 2026-07-06 13:31 | 2026-07-07 09:26 | 1500 | 756 | 3740 | 6770 |
| Kimi | Label-only | 2026-07-06 07:08 | 2026-07-06 13:31 | 1500 | 711 | 3701 | 6843 |
| Kimi | Compact-prose enrichment | 2026-07-06 07:08 | 2026-07-06 13:31 | 1500 | 706 | 3722 | 6661 |
| Kimi | Bullet-list enrichment | 2026-07-06 07:08 | 2026-07-06 13:31 | 1500 | 801 | 3760 | 6759 |
| Kimi | Markdown-table enrichment | 2026-07-06 07:08 | 2026-07-06 13:31 | 1500 | 786 | 3824 | 6713 |
| Kimi | JSON-like-schema enrichment | 2026-07-06 07:08 | 2026-07-06 13:31 | 1500 | 756 | 3740 | 6770 |

## S1.2 Duplicate and Conflict Audit

Table @tab:s1-duplicate-audit summarizes duplicate and label-conflict checks. Pair counts denote pairwise matches, whereas exclusion counts denote unique test issue identifiers; one test issue can participate in multiple train-test pairs.

Table: Duplicate and label-conflict audit summary. {#tab:s1-duplicate-audit}

| Check | Count | Note |
|---|---|---|
| Exact duplicate groups | 4 | normalized title+body, train and test combined |
| Exact train-test groups | 3 | exact groups crossing train/test |
| Exact label conflicts | 1 | exact groups with more than one label |
| Near-duplicate pairs | 33 | char-5 cosine >=0.98, exact duplicates excluded |
| Near train-test pairs | 16 | near pairs crossing train/test |
| Near label conflicts | 2 | near pairs with different labels |
| Cross-repository duplicate test issues | 0 | unique test issues in duplicate groups spanning repositories |

The prompt-injection-like repository scanner counted records matching a deliberately small case-insensitive pattern family: instructions to ignore previous or above instructions, references to a system prompt, "you are ChatGPT", `return exactly`, `output_schema`, or "developer message". It is an operational data audit, not a security proof.

Table @tab:s1-duplicate-threshold reports the char-5 cosine threshold sensitivity. The 0.98 threshold is the main audit threshold; 0.95 and 0.99 are post-result sensitivity checks.

Table: Near-duplicate threshold sensitivity. {#tab:s1-duplicate-threshold}

| Threshold | Near pairs | Train-test pairs | Conflict pairs | Removed issues | Enriched delta | Markdown delta | Question delta |
|---|---|---|---|---|---|---|---|
| 0.95 | 52 | 27 | 3 | 24 | -0.029 | -0.035 | -0.077 |
| 0.98 | 33 | 16 | 2 | 14 | -0.029 | -0.035 | -0.077 |
| 0.99 | 21 | 11 | 2 | 12 | -0.029 | -0.035 | -0.077 |

"Drop all flags" removes the union of all flagged test `issue_id` values; issues appearing in multiple flag categories are removed once.

Duplicate-exclusion sensitivity in Table @tab:s1-duplicate-sensitivity is numerically aligned with the main text: after all exact duplicate, near duplicate, train-test overlap, label-conflict, and cross-repository duplicate flags were removed, the enrichment contrast, Markdown-table versus label-only contrast, and question-class Markdown-table contrast remained negative.

Table: Duplicate-exclusion sensitivity summary. {#tab:s1-duplicate-sensitivity}

| Subset | Removed test issues | Remaining issues | Enriched vs label-only | Markdown table vs label-only | Question drop |
|---|---|---|---|---|---|
| Original | 0 | 1500 | -0.028 | -0.035 | -0.077 |
| Drop exact train-test | 3 | 1497 | -0.029 | -0.036 | -0.078 |
| Drop near train-test | 9 | 1491 | -0.028 | -0.035 | -0.077 |
| Drop label conflicts | 3 | 1497 | -0.029 | -0.035 | -0.077 |
| Drop cross-repository | 0 | 1500 | -0.028 | -0.035 | -0.077 |
| Drop all flags | 14 | 1486 | -0.029 | -0.035 | -0.077 |

## S1.3 Robustness Instruction Variants

Table @tab:s1-instruction-variants gives the P1, P2, and P3 instruction clauses used inside the same frozen user-message wrapper. Taxonomy texts are reproduced in S1.8, and their authoritative sources are `protocol/prompt_registry.yaml` and `results/tables/taxonomy_prompt_texts.csv`.

Table: Robustness instruction-clause variants. {#tab:s1-instruction-variants}

| Variant | Exact instruction text |
|---|---|
| P1 | Classify the following software issue according to TAXONOMY. |
| P2 | Assign exactly one allowed category to the software issue using TAXONOMY. |
| P3 | Determine the type of the software issue by applying TAXONOMY. |

Krippendorff's alpha is computed with nominal disagreement over the nine instruction-by-repeat runs within each system-condition cell. Exact-parser invalid or missing predictions are represented as missing values for alpha rather than as a fourth label, so exact-parser success rates are reported alongside alpha. Issues with fewer than two valid ratings are excluded from alpha's pairwise disagreement contribution by the missing-value handling in the alpha implementation.

Pairwise flip rate is the mean, over issues, of the share of unordered valid-label pairs that disagree. For each issue, disagreement is computed over all unordered pairs for which both runs produced valid exact-parser labels; if one of the two runs is invalid or missing, that pair is excluded from the denominator. Issue-level disagreement proportions are averaged equally within each system-condition cell, and cell-level summaries are averaged arithmetically. Repeat-level flip compares the three repeats within a fixed instruction variant for each issue. Instruction-variant flip compares P1, P2, and P3 while holding repeat id fixed for each issue.

Table @tab:s1-robust-contract is a post-result contract-aware sensitivity. It treats `bug`, `feature`, `question`, and `__invalid__` as four nominal states, so invalid-valid pairs count as disagreement and invalid-invalid pairs count as agreement.

Table: Contract-aware robustness agreement. {#tab:s1-robust-contract}

| System | Prompt | Parse | Alpha+invalid | Flip+invalid | Invalid share |
|---|---|---|---|---|---|
| DeepSeek | Label-only | 99.7% | 0.944 | 3.3% | 0.3% |
| DeepSeek | Bullet-list enrichment | 99.6% | 0.936 | 3.9% | 0.4% |
| DeepSeek | JSON-like-schema enrichment | 99.2% | 0.930 | 4.2% | 0.8% |
| GLM | Label-only | 99.6% | 0.957 | 2.6% | 0.4% |
| GLM | Bullet-list enrichment | 99.7% | 0.977 | 1.4% | 0.3% |
| GLM | JSON-like-schema enrichment | 99.9% | 0.974 | 1.6% | 0.1% |
| Kimi | Label-only | 100.0% | 0.933 | 4.1% | 0.0% |
| Kimi | Bullet-list enrichment | 99.2% | 0.922 | 4.7% | 0.8% |
| Kimi | JSON-like-schema enrichment | 99.3% | 0.934 | 3.9% | 0.7% |

**Table status: Post-result ranking-stability audit.** Table @tab:s1-robustness-ranks summarizes pairwise Kendall tau-b, changes in the top-ranked condition, and pairwise rank reversals across the nine instruction-by-repeat cells. These are descriptive stability measures for T0, T2, and T4; the robustness experiment did not include T1 or T3.

Table: Robustness ranking stability across instruction and repeat cells. {#tab:s1-robustness-ranks}

| System | Mean tau-b | Min tau-b | Top changes | Cell pairs | Top-change rate | Rank reversals | Opportunities | Reversal rate | Observed winners |
|---|---|---|---|---|---|---|---|---|---|
| DeepSeek V4 Flash | -0.037 | -1.000 | 26 | 36 | 72.2% | 56 | 108 | 51.9% | Label-only, Bullet-list enrichment, JSON-like-schema enrichment |
| GLM-5.2 | -0.046 | -1.000 | 24 | 36 | 66.7% | 45 | 85 | 52.9% | Label-only, Bullet-list enrichment, JSON-like-schema enrichment |
| Kimi K2.7 Code | 0.333 | -1.000 | 14 | 36 | 38.9% | 36 | 108 | 33.3% | Label-only, JSON-like-schema enrichment |

## S1.4 Secondary System and Repository Analyses

The following tables are nominal, descriptive, or post-result sensitivity analyses as indicated. They are not additional protocol-specified inferential tests.

### S1.4.1 Leave-one-out sensitivities

**Table status: Post-result sensitivity. Leave-one-repository sensitivity.** Table @tab:s1-leave-one-repository is a post-result leave-one-repository sensitivity.

Table: Leave-one-repository enrichment sensitivity. {#tab:s1-leave-one-repository}

| Excluded repository | Mean enriched vs label-only | Negative blocks | Blocks |
|---|---|---|---|
| bitcoin | -0.028 | 11 | 12 |
| react | -0.031 | 10 | 12 |
| vscode | -0.031 | 11 | 12 |
| opencv | -0.028 | 10 | 12 |
| tensorflow | -0.024 | 10 | 12 |

**Table status: Post-result sensitivity. Leave-one-system sensitivity.** Table @tab:s1-leave-one-model is a post-result leave-one-system sensitivity.

Table: Leave-one-system enrichment sensitivity. {#tab:s1-leave-one-model}

| Excluded system | Mean enriched vs label-only | Negative blocks | Blocks |
|---|---|---|---|
| DeepSeek V4 Flash | -0.036 | 10 | 10 |
| GLM-5.2 | -0.030 | 8 | 10 |
| Kimi K2.7 Code | -0.019 | 8 | 10 |

Tables @tab:s1-revision-leave-repository and @tab:s1-revision-leave-system expand the audit to all four T1--T4 versus T0 contrasts. They are point-estimate sensitivities only; no crossed-cell interval is attached. Every leave-one-out contrast remained negative.

Table: Four main contrasts after excluding each repository. {#tab:s1-revision-leave-repository}

| Excluded repository | Comparison | Observed delta | Negative cells | Remaining cells |
|---|---|---|---|---|
| bitcoin | Compact-prose enrichment vs label-only | -0.021 | 10 | 12 |
| bitcoin | Bullet-list enrichment vs label-only | -0.027 | 10 | 12 |
| bitcoin | Markdown-table enrichment vs label-only | -0.035 | 12 | 12 |
| bitcoin | JSON-like-schema enrichment vs label-only | -0.031 | 11 | 12 |
| react | Compact-prose enrichment vs label-only | -0.026 | 11 | 12 |
| react | Bullet-list enrichment vs label-only | -0.028 | 9 | 12 |
| react | Markdown-table enrichment vs label-only | -0.040 | 12 | 12 |
| react | JSON-like-schema enrichment vs label-only | -0.032 | 10 | 12 |
| vscode | Compact-prose enrichment vs label-only | -0.026 | 11 | 12 |
| vscode | Bullet-list enrichment vs label-only | -0.028 | 10 | 12 |
| vscode | Markdown-table enrichment vs label-only | -0.036 | 12 | 12 |
| vscode | JSON-like-schema enrichment vs label-only | -0.033 | 11 | 12 |
| opencv | Compact-prose enrichment vs label-only | -0.022 | 10 | 12 |
| opencv | Bullet-list enrichment vs label-only | -0.026 | 10 | 12 |
| opencv | Markdown-table enrichment vs label-only | -0.036 | 12 | 12 |
| opencv | JSON-like-schema enrichment vs label-only | -0.026 | 10 | 12 |
| tensorflow | Compact-prose enrichment vs label-only | -0.016 | 10 | 12 |
| tensorflow | Bullet-list enrichment vs label-only | -0.024 | 9 | 12 |
| tensorflow | Markdown-table enrichment vs label-only | -0.030 | 12 | 12 |
| tensorflow | JSON-like-schema enrichment vs label-only | -0.027 | 10 | 12 |

Table: Four main contrasts after excluding each provider-facing system. {#tab:s1-revision-leave-system}

| Excluded system | Comparison | Observed delta | Negative cells | Remaining cells |
|---|---|---|---|---|
| DeepSeek | Compact-prose enrichment vs label-only | -0.027 | 10 | 10 |
| DeepSeek | Bullet-list enrichment vs label-only | -0.036 | 10 | 10 |
| DeepSeek | Markdown-table enrichment vs label-only | -0.041 | 10 | 10 |
| DeepSeek | JSON-like-schema enrichment vs label-only | -0.040 | 10 | 10 |
| GLM | Compact-prose enrichment vs label-only | -0.022 | 8 | 10 |
| GLM | Bullet-list enrichment vs label-only | -0.028 | 7 | 10 |
| GLM | Markdown-table enrichment vs label-only | -0.039 | 10 | 10 |
| GLM | JSON-like-schema enrichment vs label-only | -0.033 | 8 | 10 |
| Kimi | Compact-prose enrichment vs label-only | -0.018 | 8 | 10 |
| Kimi | Bullet-list enrichment vs label-only | -0.016 | 7 | 10 |
| Kimi | Markdown-table enrichment vs label-only | -0.026 | 10 | 10 |
| Kimi | JSON-like-schema enrichment vs label-only | -0.017 | 8 | 10 |

Table @tab:s1-revision-robustness-sample gives all four canonical main-P1 contrasts on exactly the 150 issues used by the original robustness run and targeted extension. It remains a sampling-composition comparator: the original same-sample T3--T0 value is reported beside, but not pooled with, the three new targeted repeats in S1.11.

Table: Canonical-instruction main contrasts on the fixed 150-issue robustness sample. {#tab:s1-revision-robustness-sample}

| Comparison | Observed delta | Negative cells | Cells | Issues |
|---|---|---|---|---|
| Compact-prose enrichment vs label-only | -0.007 | 7 | 15 | 150 |
| Bullet-list enrichment vs label-only | 0.007 | 3 | 15 | 150 |
| Markdown-table enrichment vs label-only | -0.017 | 7 | 15 | 150 |
| JSON-like-schema enrichment vs label-only | 0.001 | 4 | 15 | 150 |

### S1.4.2 Fixed-repository and repository-resampling bootstrap outputs

**Historical protocol outputs--no inferential weight.**

The original crossed-cell Friedman output was chi-square=27.147, n=15, and p=$1.86 \times 10^{-5}$. Table @tab:protocol-effects preserves the four original Wilcoxon contrasts and Holm adjustment. Because the 15 repository-by-system cells share repositories and provider-facing systems, neither historical output is used as inferential evidence.

Table: Historical protocol block outputs; retained for audit and not used as inferential evidence. {#tab:protocol-effects}

| Comparison | Mean delta | Median delta | Paired dz | Rank-biserial | Crossed cells | Raw p | Holm p |
|---|---|---|---|---|---|---|---|
| Compact-prose enrichment vs label-only | -0.022 | -0.018 | -0.979 | -0.850 | 15 | 0.0020 | 0.0031 |
| Bullet-list enrichment vs label-only | -0.027 | -0.024 | -1.104 | -0.867 | 15 | 0.0015 | 0.0031 |
| Markdown-table enrichment vs label-only | -0.035 | -0.032 | -1.361 | -1.000 | 15 | $6.10 \times 10^{-5}$ | $2.44 \times 10^{-4}$ |
| JSON-like-schema enrichment vs label-only | -0.030 | -0.024 | -1.087 | -0.900 | 15 | $8.54 \times 10^{-4}$ | 0.0026 |

**Post-result conditional bootstrap sensitivities.**

The fixed-repository bootstrap and repository-resampling bootstrap intentionally target different estimands. The fixed-repository observed statistic computes Macro-F1 within each system-repository cell, forms paired condition deltas, and averages the five repositories and three provider-facing systems with equal cell weight. Its percentile interval resamples issue ids within each fixed repository while carrying all system-condition predictions for a sampled issue together.

Table @tab:s1-fixed-bootstrap is a post-result condition-specific fixed-benchmark stability analysis. The four-condition family uses simultaneous max-deviation 95% and 90% intervals. These are conditional issue-composition intervals for the fixed repositories and systems, not population intervals.

Table: Fixed-repository bootstrap output. {#tab:s1-fixed-bootstrap}

| Comparison | Observed delta | Nominal 95% interval | Simultaneous 95% interval | Simultaneous 90% interval | Draws | Seed |
|---|---|---|---|---|---|---|
| Compact-prose enrichment vs label-only | -0.022 | [-0.031, -0.014] | [-0.033, -0.011] | [-0.032, -0.013] | 10,000 | 20260704 |
| Bullet-list enrichment vs label-only | -0.027 | [-0.035, -0.019] | [-0.038, -0.016] | [-0.036, -0.017] | 10,000 | 20260704 |
| Markdown-table enrichment vs label-only | -0.035 | [-0.045, -0.025] | [-0.046, -0.024] | [-0.045, -0.026] | 10,000 | 20260704 |
| JSON-like-schema enrichment vs label-only | -0.030 | [-0.039, -0.021] | [-0.041, -0.019] | [-0.039, -0.020] | 10,000 | 20260704 |

**Protocol RQ5 status: Demoted supplementary descriptive audit.** The simultaneous 90% intervals for all four enriched-versus-label-only contrasts lay entirely below -0.01. The Markdown-table and JSON-like-schema intervals also lay entirely below -0.02, whereas the compact-prose and bullet-list intervals crossed -0.02. The +/-0.01 and +/-0.02 margins were specified before results but lack external minimal-important-difference validation. This comparison is not a formal equivalence test, is not used as a standalone main-text research question, and does not establish practical importance in new repositories or systems.

The separately reported aggregate fixed-repository interval is nominal because it is outside the simultaneous four-contrast family. The repository-resampling sensitivity first pools system predictions within sampled repositories and then resamples repositories before issue ids. Its observed delta is therefore a superpopulation-oriented pooled estimand, not the equal-weight system-repository estimand above; small observed-delta differences between Tables @tab:s1-fixed-bootstrap and @tab:s1-clustered-bootstrap are expected from this weighting difference. The repository-resampling 95% intervals are nominal and unadjusted. Both analyses use 10,000 draws with seed 20260704.

Table @tab:s1-clustered-bootstrap is a post-result superpopulation-oriented repository-resampling bootstrap sensitivity.

Table: Repository-resampling bootstrap output. {#tab:s1-clustered-bootstrap}

| Comparison | Observed delta | 95% interval | Reference reading |
|---|---|---|---|
| Compact-prose enrichment vs label-only | -0.0234 | [-0.0392, -0.0083] | CI negative; crosses -0.02 ref. |
| Bullet-list enrichment vs label-only | -0.0272 | [-0.0373, -0.0175] | CI negative; crosses -0.02 ref. |
| Markdown-table enrichment vs label-only | -0.0354 | [-0.0508, -0.0205] | CI below -0.02 ref. |
| JSON-like-schema enrichment vs label-only | -0.0307 | [-0.0438, -0.0180] | CI negative; crosses -0.02 ref. |
| Mean enriched vs label-only | -0.0292 | [-0.0412, -0.0175] | CI negative; crosses -0.02 ref. |

Table @tab:s1-independence gives the descriptive direction and dependence summary.

Table: Direction and dependence sensitivity summary. {#tab:s1-independence}

| Comparison | Negative cells | Cells | Negative repositories | Repositories | Negative systems | Systems | Repository-resampling 95% interval |
|---|---|---|---|---|---|---|---|
| Compact-prose enrichment vs label-only | 13 | 15 | 5 | 5 | 3 | 3 | [-0.039, -0.008] |
| Bullet-list enrichment vs label-only | 12 | 15 | 5 | 5 | 3 | 3 | [-0.037, -0.018] |
| Markdown-table enrichment vs label-only | 15 | 15 | 5 | 5 | 3 | 3 | [-0.051, -0.020] |
| JSON-like-schema enrichment vs label-only | 13 | 15 | 5 | 5 | 3 | 3 | [-0.044, -0.018] |
| Mean enriched vs label-only | 13 | 15 | 5 | 5 | 3 | 3 | [-0.041, -0.017] |

### S1.4.3 System heterogeneity and difference intervals

Tables @tab:model-interaction and @tab:model-rankings report the descriptive interaction ranges and point-estimate provider-facing system rankings moved from the main text. They are audit-oriented summaries, not evidence of system superiority.

Table: Range of taxonomy-prompt effects across provider-facing systems. {#tab:model-interaction}

| Comparison | Min system delta | Max system delta | Range |
|---|---|---|---|
| Mean enriched vs label-only | -0.047 | -0.013 | 0.034 |
| Compact-prose enrichment vs label-only | -0.031 | -0.013 | 0.018 |
| Bullet-list enrichment vs label-only | -0.047 | -0.009 | 0.038 |
| Markdown-table enrichment vs label-only | -0.054 | -0.023 | 0.031 |
| JSON-like-schema enrichment vs label-only | -0.056 | -0.009 | 0.047 |

Table: Point-estimate provider-facing system ranking by taxonomy prompt. {#tab:model-rankings}

| Prompt | System ranking | Macro-F1 values |
|---|---|---|
| Label-only | Kimi > GLM > DeepSeek | Kimi=0.759; GLM=0.738; DeepSeek=0.708 |
| Compact-prose enrichment | Kimi > GLM > DeepSeek | Kimi=0.727; GLM=0.715; DeepSeek=0.694 |
| Bullet-list enrichment | GLM > Kimi > DeepSeek | GLM=0.714; Kimi=0.710; DeepSeek=0.700 |
| Markdown-table enrichment | GLM > Kimi > DeepSeek | GLM=0.711; Kimi=0.704; DeepSeek=0.684 |
| JSON-like-schema enrichment | GLM > Kimi > DeepSeek | GLM=0.713; Kimi=0.702; DeepSeek=0.699 |

**Table status: Nominal descriptive intervals. Not multiplicity-adjusted; no superiority claim.** For each prompt, Table @tab:s1-model-pairwise resamples the five repositories with replacement and then resamples issue ids within every sampled repository, carrying the paired system predictions for each sampled issue together. It reports nominal, unadjusted 95% percentile intervals from 10,000 draws with seed 20260704.

Table: Nominal system-difference intervals by taxonomy prompt. {#tab:s1-model-pairwise}

| Prompt | System contrast | Observed delta | Nominal 95% interval |
|---|---|---|---|
| Label-only | GLM-Kimi | -0.021 | [-0.046, 0.002] |
| Label-only | Kimi-DeepSeek | 0.051 | [0.026, 0.077] |
| Label-only | GLM-DeepSeek | 0.029 | [0.002, 0.060] |
| Compact-prose enrichment | GLM-Kimi | -0.011 | [-0.033, 0.010] |
| Compact-prose enrichment | Kimi-DeepSeek | 0.033 | [0.015, 0.051] |
| Compact-prose enrichment | GLM-DeepSeek | 0.022 | [-0.003, 0.049] |
| Bullet-list enrichment | GLM-Kimi | 0.004 | [-0.016, 0.023] |
| Bullet-list enrichment | Kimi-DeepSeek | 0.010 | [-0.008, 0.030] |
| Bullet-list enrichment | GLM-DeepSeek | 0.014 | [-0.008, 0.034] |
| Markdown-table enrichment | GLM-Kimi | 0.007 | [-0.009, 0.023] |
| Markdown-table enrichment | Kimi-DeepSeek | 0.020 | [0.001, 0.039] |
| Markdown-table enrichment | GLM-DeepSeek | 0.027 | [0.009, 0.046] |
| JSON-like-schema enrichment | GLM-Kimi | 0.011 | [-0.004, 0.027] |
| JSON-like-schema enrichment | Kimi-DeepSeek | 0.003 | [-0.014, 0.020] |
| JSON-like-schema enrichment | GLM-DeepSeek | 0.015 | [-0.000, 0.033] |

### S1.4.4 Leave-one-repository-out selector

Table @tab:s1-heldout-selector reports the deployment-oriented leave-one-repository-out validation check. Selection uses the equal-weight arithmetic mean of source-repository Macro-F1 values, followed by lower repository-mean invalid rate, lower mean input-token count, and T0-T4 order. Correcting the earlier pooled-source implementation changed none of the 15 selected prompts.

Table: Leave-one-repository-out selector folds. {#tab:s1-heldout-selector}

| System | Target | Selected | Oracle | Selected F1 | Oracle F1 | Regret |
|---|---|---|---|---|---|---|
| DeepSeek V4 Flash | bitcoin | Label-only | Bullet-list enrichment | 0.696 | 0.711 | 0.015 |
| DeepSeek V4 Flash | react | Label-only | Compact-prose enrichment | 0.767 | 0.769 | 0.002 |
| DeepSeek V4 Flash | vscode | Label-only | Compact-prose enrichment | 0.588 | 0.606 | 0.018 |
| DeepSeek V4 Flash | opencv | Label-only | Bullet-list enrichment | 0.702 | 0.706 | 0.004 |
| DeepSeek V4 Flash | tensorflow | Label-only | Label-only | 0.759 | 0.759 | 0.000 |
| GLM-5.2 | bitcoin | Label-only | Label-only | 0.719 | 0.719 | 0.000 |
| GLM-5.2 | react | Label-only | Label-only | 0.789 | 0.789 | 0.000 |
| GLM-5.2 | vscode | Label-only | Label-only | 0.638 | 0.638 | 0.000 |
| GLM-5.2 | opencv | Label-only | Label-only | 0.774 | 0.774 | 0.000 |
| GLM-5.2 | tensorflow | Label-only | Label-only | 0.750 | 0.750 | 0.000 |
| Kimi K2.7 Code | bitcoin | Label-only | Label-only | 0.777 | 0.777 | 0.000 |
| Kimi K2.7 Code | react | Label-only | Label-only | 0.790 | 0.790 | 0.000 |
| Kimi K2.7 Code | vscode | Label-only | Label-only | 0.640 | 0.640 | 0.000 |
| Kimi K2.7 Code | opencv | Label-only | Label-only | 0.774 | 0.774 | 0.000 |
| Kimi K2.7 Code | tensorflow | Label-only | Label-only | 0.788 | 0.788 | 0.000 |

Table @tab:s1-heldout-bootstrap reports a post-result repository-stratified issue bootstrap. Every draw resamples issues within each fixed train and test repository, recomputes the source-repository-only selector, and reevaluates gain and oracle regret on the resampled target repository. The intervals therefore describe issue-composition sensitivity within these fixed repositories, not transfer to new repositories.

Table: Leave-one-repository-out selector bootstrap summary. {#tab:s1-heldout-bootstrap}

| Metric | Observed | Bootstrap 95% interval |
|---|---|---|
| Mean selected-minus-label-only gain | 0.000 | [-0.007, 0.001] |
| Median selected-minus-label-only gain | 0.000 | [0.000, 0.000] |
| Mean oracle regret | 0.003 | [0.002, 0.013] |
| Median oracle regret | 0.000 | [0.000, 0.004] |
| Selected above label-only rate | 0.0% | [0.0%, 20.0%] |
| Selected equals oracle rate | 73.3% | [40.0%, 80.0%] |
| Label-only selection rate | 100.0% | [66.7%, 100.0%] |
| Compact-prose selection rate | 0.0% | [0.0%, 20.0%] |
| Bullet-list selection rate | 0.0% | [0.0%, 33.3%] |
| Markdown-table selection rate | 0.0% | [0.0%, 0.0%] |
| JSON-like-schema selection rate | 0.0% | [0.0%, 6.7%] |

### S1.4.5 Valid-paired analyses

Table @tab:s1-model-valid-paired reports the descriptive system-stratified both-valid sensitivity analysis. Because output validity is observed after the prompt treatment, conditioning on both outputs being valid can induce selection bias; the table is not a causal decomposition of parsing and classification effects.

Table: System-stratified valid-paired deltas. {#tab:s1-model-valid-paired}

| System | Comparison | Contract delta | Valid-paired delta | Valid pair rate |
|---|---|---|---|---|
| DeepSeek V4 Flash | Compact-prose enrichment vs label-only | -0.014 | -0.009 | 97.8% |
| GLM-5.2 | Compact-prose enrichment vs label-only | -0.022 | -0.022 | 98.5% |
| Kimi K2.7 Code | Compact-prose enrichment vs label-only | -0.032 | -0.028 | 98.9% |
| DeepSeek V4 Flash | Bullet-list enrichment vs label-only | -0.008 | -0.004 | 98.3% |
| GLM-5.2 | Bullet-list enrichment vs label-only | -0.024 | -0.022 | 98.4% |
| Kimi K2.7 Code | Bullet-list enrichment vs label-only | -0.049 | -0.047 | 99.0% |
| DeepSeek V4 Flash | Markdown-table enrichment vs label-only | -0.024 | -0.018 | 97.8% |
| GLM-5.2 | Markdown-table enrichment vs label-only | -0.026 | -0.027 | 98.9% |
| Kimi K2.7 Code | Markdown-table enrichment vs label-only | -0.055 | -0.049 | 98.7% |
| DeepSeek V4 Flash | JSON-like-schema enrichment vs label-only | -0.010 | -0.003 | 97.5% |
| GLM-5.2 | JSON-like-schema enrichment vs label-only | -0.024 | -0.023 | 98.7% |
| Kimi K2.7 Code | JSON-like-schema enrichment vs label-only | -0.057 | -0.051 | 98.6% |

### S1.4.6 Contextual supervised baseline

Table @tab:s1-baseline-context is a non-comparable contextual performance reference. Supervised TF-IDF + Linear SVM results are contextual references and are not used for direct system-ranking claims. For LLM rows, pooled global Macro-F1 is computed from the concatenated predictions across all three provider-facing system aliases within the condition; repository-mean Macro-F1 is the equal-weight mean over repository-by-system cells. For the SVM row, pooled global Macro-F1 is computed over all 1,500 test issues from the single train-all/test-all classifier; repository-mean Macro-F1 is the equal-weight mean over the five repository cells.

Table: Contextual supervised baseline and LLM aggregation reference. {#tab:s1-baseline-context}

| System | Condition/setting | Pooled global Macro-F1 | Repository-mean Macro-F1 | Interpretation |
|---|---|---|---|---|
| LLM zero-shot pooled across three provider-facing system aliases | Label-only | 0.735 | 0.730 | contextual descriptive reference; not a direct supervised-baseline ranking claim |
| LLM zero-shot pooled across three provider-facing system aliases | Compact-prose enrichment | 0.712 | 0.708 | contextual descriptive reference; not a direct supervised-baseline ranking claim |
| LLM zero-shot pooled across three provider-facing system aliases | Bullet-list enrichment | 0.708 | 0.704 | contextual descriptive reference; not a direct supervised-baseline ranking claim |
| LLM zero-shot pooled across three provider-facing system aliases | Markdown-table enrichment | 0.700 | 0.695 | contextual descriptive reference; not a direct supervised-baseline ranking claim |
| LLM zero-shot pooled across three provider-facing system aliases | JSON-like-schema enrichment | 0.705 | 0.700 | contextual descriptive reference; not a direct supervised-baseline ranking claim |
| Supervised TF-IDF + Linear SVM | train-all test-all contextual baseline | 0.747 | 0.746 | contextual descriptive reference; not a direct zero-shot LLM system-ranking claim |

### S1.4.7 Invalid-output and token audit

**Table status: Operational audit. Invalid-output categories.** Table @tab:s1-invalid-categories reports operational invalid-output categories.

Table: Invalid-output categories by taxonomy prompt. {#tab:s1-invalid-categories}

| Prompt | Category | Count |
|---|---|---|
| Label-only | empty | 11 |
| Label-only | explanatory/multilabel | 3 |
| Compact-prose enrichment | empty | 50 |
| Compact-prose enrichment | explanatory/multilabel | 7 |
| Compact-prose enrichment | malformed JSON, one label | 1 |
| Bullet-list enrichment | empty | 41 |
| Bullet-list enrichment | explanatory/multilabel | 5 |
| Bullet-list enrichment | malformed JSON, one label | 6 |
| Markdown-table enrichment | empty | 51 |
| Markdown-table enrichment | explanatory/multilabel | 3 |
| Markdown-table enrichment | malformed JSON, no label | 1 |
| JSON-like-schema enrichment | empty | 61 |
| JSON-like-schema enrichment | explanatory/multilabel | 4 |

**Table status: Operational audit. Completion-token and visible-output diagnostics.** Table @tab:s1-empty-output reports completion-token and visible-output diagnostics.

Comp. tok. is the median provider-reported completion-token count over all completed responses in the system-prompt cell. Empty tok. is the median provider-reported completion-token count among empty visible responses in that cell. Visible chars is the median preserved assistant-message character count. Provider-reported token usage may differ by route and is not a re-tokenization of the visible string; 1025 is reported as the observed provider-reported value where it appears.

Table: Completion-token and visible-output diagnostics by system and prompt. {#tab:s1-empty-output}

| System | Prompt | Empty | Invalid | Comp. tok. | Empty tok. | Visible chars | Empty rate |
|---|---|---|---|---|---|---|---|
| DeepSeek | Label-only | 5 | 5 | 146.500 | 1024.000 | 16.000 | 0.3% |
| DeepSeek | Compact-prose enrichment | 28 | 29 | 193.000 | 1024.000 | 16.000 | 1.9% |
| DeepSeek | Bullet-list enrichment | 21 | 22 | 185.500 | 1024.000 | 16.000 | 1.4% |
| DeepSeek | Markdown-table enrichment | 28 | 28 | 198.000 | 1024.000 | 16.000 | 1.9% |
| DeepSeek | JSON-like-schema enrichment | 34 | 34 | 222.000 | 1024.000 | 16.000 | 2.3% |
| GLM | Label-only | 6 | 9 | 67.000 | 1025.000 | 19.000 | 0.4% |
| GLM | Compact-prose enrichment | 6 | 13 | 65.000 | 1025.000 | 16.000 | 0.4% |
| GLM | Bullet-list enrichment | 5 | 15 | 69.000 | 1025.000 | 16.000 | 0.3% |
| GLM | Markdown-table enrichment | 4 | 7 | 67.000 | 1025.000 | 16.000 | 0.3% |
| GLM | JSON-like-schema enrichment | 6 | 10 | 62.500 | 1025.000 | 16.000 | 0.4% |
| Kimi | Label-only | 0 | 0 | 145.000 |  | 20.000 | 0.0% |
| Kimi | Compact-prose enrichment | 16 | 16 | 201.500 | 1024.000 | 16.000 | 1.1% |
| Kimi | Bullet-list enrichment | 15 | 15 | 201.000 | 1024.000 | 16.000 | 1.0% |
| Kimi | Markdown-table enrichment | 19 | 20 | 220.000 | 1024.000 | 16.000 | 1.3% |
| Kimi | JSON-like-schema enrichment | 21 | 21 | 210.500 | 1024.000 | 16.000 | 1.4% |

## S1.5 Reproducibility Map

Table @tab:s1-analysis-status preserves the protocol-to-manuscript distinction between prespecified, post-result, modified, and omitted analyses. Items marked not implemented remain explicit omissions and are not silently replaced by later diagnostics.

Table: Protocol analysis-status map. {#tab:s1-analysis-status}

| Protocol item | Analysis status | Reported or omitted |
|---|---|---|
| RQ1 performance | Prespecified contrasts; post-result dependence-preserving sensitivity | Four T1-T4 vs T0 effects reported with issue-cluster condition-label permutation, max-statistic family adjustment, and simultaneous intervals; original crossed-cell Friedman/Wilcoxon outputs retained only as protocol history |
| Enriched-representation comparison | Post-result exploratory | Nominal pairwise intervals and descriptive ranks; not an RQ or independent format test |
| RQ2 output compliance | Prespecified endpoint; post-result dependence-preserving sensitivity | Exact, lenient, invalid, and both-valid summaries plus issue-cluster condition-label permutation, max-statistic adjustment, absolute risk differences, and simultaneous intervals reported; original Cochran Q/McNemar forms not used |
| RQ3 leave-one-repository-out selection | Prespecified selector reported; bootstrap completed after result visibility | Equal-weight source-repository selector and oracle regret reported; repository-stratified issue bootstrap recomputes selection and target metrics in every draw |
| RQ4 prompt robustness | Prespecified summaries completed after result visibility | Alpha, issue-bootstrap intervals, flip rates, normalized entropy, parse rates, performance deltas, Kendall tau-b, rank reversals, and top-condition changes reported for the original T0/T2/T4 robustness matrix |
| Targeted T0-T3 repeated-run extension | Post-result, budget-constrained extension; completed through a committed missing-task recovery | The first segment stopped pre-result at 1,640/2,700 after an SDK-metering defect; a max_retries=0 recovery ran only the 1,060 missing frozen keys. All 2,700 tasks were frozen before targeted gold access; repeat-specific, agreement, parsing, bootstrap, provenance, and budget results are reported without rescue subsets |
| Provider, retry/resume, and access-window audit | Post-result descriptive operational audit; no new inference | Canonical-task history, recovered terminal errors, response-model and anonymized invocation segments, fixed six-hour UTC windows, contrast-specific GLM matched subsets, and leave-one-system checks reported without causal attribution |
| RQ5 descriptive reference-band assessment | Protocol question demoted to supplementary descriptive audit | Post-result simultaneous 90% fixed-benchmark intervals are compared with the prespecified but externally unvalidated +/-0.01 and +/-0.02 margins in S1.4.2; no standalone main-text RQ or general minimal-important-difference claim |
| Prespecified per-model issue bootstrap and correctness tests | Not implemented in the protocol form | Model-stratified repository summaries and direction checks reported; per-model repository-stratified issue bootstrap and Cochran Q/McNemar correctness tests remain omitted and are not replaced by population claims |
| Second supervised baseline | Not implemented | TF-IDF + Linear SVM contextual baseline reported; the suggested SetFit/Sentence-Transformer baseline was not implemented and is not claimed |

Every numbered table in S1 is regenerated by the same command chain as the manuscript. No new LLM inference is run by these commands; all numbers come from preserved prediction, data, metric, and analysis artifacts. Table @tab:s1-repro-map uses short artifact names; unless otherwise stated, table outputs are under `results/tables/`.

```bash
uv sync --frozen
uv run taxrep data download
uv run taxrep data validate
uv run taxrep parse
uv run taxrep evaluate
uv run taxrep held-out
uv run taxrep statistics
uv run taxrep figures
uv run taxrep targeted analyze
uv run taxrep targeted audit
uv run python scripts/build_paper_artifacts.py
uv run taxrep verify
```

Table: Supplementary-table reproducibility map. {#tab:s1-repro-map}

| S1 item | Input artifact | Script | Output | Seed |
|---|---|---|---|---|
| S1.1 | parsed predictions | run-order audit | condition interleaving by system | 20260704 |
| S1.2 | train/test gold; parsed predictions | duplicate audit; threshold sensitivity | duplicate audit; duplicate sensitivity | 20260704 |
| S1.3 | prompt registry; parsed predictions | instruction variants; robustness bootstrap and rank stability | instruction texts; agreement intervals; entropy; ranks | sample/analysis: 20260704; generation: 1103/2207/3301 |
| S1.4 | parsed predictions; train/test gold | fixed-benchmark permutation; selector bootstrap; held-out | max-statistic inference; leave-one; held-out; baseline | 20260704 |
| S1.5 | same frozen artifacts | paper build; taxrep verify | manuscript and S1 PDFs; verify report | 20260704 |
| S1.6 | block metrics; frozen parsed predictions | enriched-format and repository-rank analyses | representation-rank tables and artifacts | 20260704 |
| S1.7 | model registry; canonical Parquet; append-only JSONL and manifests | uv run taxrep revision-audit; paper build | task history, response-model, provenance, access-window, and leave-one-out tables | request metadata |
| S1.8 | prompt registry; taxonomy text export | prompt-text export | complete taxonomy text blocks | not applicable |
| S1.9 | prompt registry; hash manifest; run configs; provider adapter | prompt render and hash audit | templates, route-specific payload policy, and full hashes | generation policy shown |
| S1.10 | Koyuncu (2026) full text; frozen study protocol | design comparison audit | closest-study design comparison | not applicable |
| S1.11 | two targeted raw segments; result freeze; recovery and call-ledger manifests | targeted recovery preflight/inference; result freeze; targeted analyze and audit | repeat, system, repository, agreement, bootstrap, provenance, and budget tables | task order: 20260711; requested generation: 4409/5501/6607 |

## S1.6 Exploratory Enriched-Representation Check

The enriched-prompt Friedman result is a post-result exploratory analysis rather than protocol RQ2 or an independent inferential family: chi-square=11.720, df=3, n=15, p=0.0084. Because the 15 cells share repositories and provider-facing systems, this omnibus p-value is not treated as independent-cell inferential evidence. The main text interprets enriched-prompt differences through nominal repository-clustered pairwise intervals. Table @tab:s1-representation-repository-ranks gives the repository-level rankings that were moved out of the main text to reduce table density.

Table: Repository-level rankings among enriched representations. {#tab:s1-representation-repository-ranks}

| Repository | Enriched prompt order | Macro-F1 values |
|---|---|---|
| bitcoin | JSON-like-schema enrichment > Bullet-list enrichment > Compact-prose enrichment > Markdown-table enrichment | JSON-like-schema enrichment=0.706; Bullet-list enrichment=0.704; Compact-prose enrichment=0.704; Markdown-table enrichment=0.693 |
| react | Compact-prose enrichment > Markdown-table enrichment > Bullet-list enrichment > JSON-like-schema enrichment | Compact-prose enrichment=0.776; Markdown-table enrichment=0.766; Bullet-list enrichment=0.760; JSON-like-schema enrichment=0.760 |
| vscode | Compact-prose enrichment > JSON-like-schema enrichment > Bullet-list enrichment > Markdown-table enrichment | Compact-prose enrichment=0.613; JSON-like-schema enrichment=0.605; Bullet-list enrichment=0.603; Markdown-table enrichment=0.589 |
| opencv | Compact-prose enrichment > Bullet-list enrichment > Markdown-table enrichment > JSON-like-schema enrichment | Compact-prose enrichment=0.727; Bullet-list enrichment=0.723; Markdown-table enrichment=0.717; JSON-like-schema enrichment=0.705 |
| tensorflow | Bullet-list enrichment > JSON-like-schema enrichment > Compact-prose enrichment > Markdown-table enrichment | Bullet-list enrichment=0.727; JSON-like-schema enrichment=0.725; Compact-prose enrichment=0.719; Markdown-table enrichment=0.709 |

## S1.7 Provider, API, and Retry Audit

Table @tab:s1-truncation reports the canonical-row input-token and local preprocessing-truncation audit. `was_truncated=false` means that the repository preprocessing pipeline did not shorten the serialized input; it does not prove an immutable upstream context limit for a mutable provider alias.

Table: Canonical-run input-token and preprocessing-truncation audit. {#tab:s1-truncation}

| Run | Split | Rows | Truncated | Median input tokens | Max input tokens | Interpretation |
|---|---|---|---|---|---|---|
| main | test | 22500 | 0 | 737 | 26994 | no preprocessing truncation occurred |
| robustness | test | 12150 | 0 | 725 | 22101 | no preprocessing truncation occurred |
| train-selection | train | 22500 | 0 | 730 | 87051 | no preprocessing truncation occurred |

Table @tab:s1-model-api records the request-parameter surface that can be audited from completed main and robustness rows and the model registry. Robustness repeats used three distinct prespecified generation-seed requests: repeat 1 used 1103, repeat 2 used 2207, and repeat 3 used 3301. The seed field was sent in every completed robustness row and accepted by the gateway, but upstream deterministic enforcement was not independently verifiable. Kimi received neither temperature nor top-p, so its robustness decoding settings are provider defaults rather than observed low-temperature settings. Immutable checkpoint hashes, `finish_reason`, system fingerprints, and hidden-token splits were not exposed or not retained by the frozen adapter.

The physical robustness JSONL history contains 13,225 records: 12,150 successful records and 1,075 preserved terminal technical-error checkpoints. Canonical analysis retains one successful record per task, yielding the reported 12,150 completed tasks. Seed and decoding assertions refer to those completed canonical rows; failed checkpoint rows have no completed request-parameter flags.

Table: Route-specific API-parameter and generation-seed audit. {#tab:s1-model-api}

| System | Main temp | Robust temp | Main top_p | Robust top_p | Robust generation seeds | Generation-seed evidence | API cap | Catalog SHA-256 prefix |
|---|---|---|---|---|---|---|---|---|
| DeepSeek | 0.0 sent | 0.2 sent | 1.0 sent | 1.0 sent | r1=1103; r2=2207; r3=3301 | field accepted; upstream enforcement unverified | 1024 | ea31ec633e02 |
| GLM | 0.0 sent | 0.2 sent | 1.0 sent | 1.0 sent | r1=1103; r2=2207; r3=3301 | field accepted; upstream enforcement unverified | 1024 | ea31ec633e02 |
| Kimi | 0.0 omitted; provider default unknown | 0.2 omitted; provider default unknown | 1.0 omitted; provider default unknown | 1.0 omitted; provider default unknown | r1=1103; r2=2207; r3=3301 | field accepted; upstream enforcement unverified | 1024 | ea31ec633e02 |

Table @tab:s1-glm-backend-balance makes the condition-by-response-model counts auditable. The counts are similar across conditions, which limits but does not eliminate route confounding.

Table: GLM response-model field counts by taxonomy prompt. {#tab:s1-glm-backend-balance}

| Prompt | Fireworks GLM | frank/GLM-5.2 | glm-5.2 |
|---|---|---|---|
| Label-only | 604 | 769 | 127 |
| Compact-prose enrichment | 591 | 767 | 142 |
| Bullet-list enrichment | 600 | 758 | 142 |
| Markdown-table enrichment | 600 | 746 | 154 |
| JSON-like-schema enrichment | 614 | 760 | 126 |

GLM-5.2 was a gateway alias rather than an immutable checkpoint. Main responses retained three provider `model` strings (accounts/fireworks/models/glm-5p2=3009; frank/GLM-5.2=3800; glm-5.2=691), and the run resumed with a different OpenCode Go account after a usage-limit event. Requests for all five taxonomy conditions were deterministically interleaved. Table @tab:s1-revision-glm-pairwise uses each Tj--T0 response-model or inferred-resume-segment intersection separately rather than requiring all five conditions on the same issue. The matched counts are consequently larger for the dominant route, but these remain post-result provenance diagnostics: account, time, response-model routing, and issue composition cannot be separated causally.

Table: GLM contrast-specific matched provenance sensitivities. {#tab:s1-revision-glm-pairwise}

| Dimension | Subset | Contrast | Matched issues | Repositories | Equal-repository delta | Negative repositories |
|---|---|---|---|---|---|---|
| resume segment | invocation_001 | T1-T0 | 538 | 5 | -0.027 | 5 |
| resume segment | invocation_001 | T2-T0 | 538 | 5 | -0.022 | 5 |
| resume segment | invocation_001 | T3-T0 | 558 | 5 | -0.030 | 5 |
| resume segment | invocation_001 | T4-T0 | 512 | 5 | -0.027 | 5 |
| resume segment | invocation_004 | T1-T0 | 233 | 5 | -0.017 | 4 |
| resume segment | invocation_004 | T2-T0 | 242 | 5 | -0.038 | 5 |
| resume segment | invocation_004 | T3-T0 | 262 | 5 | -0.008 | 3 |
| resume segment | invocation_004 | T4-T0 | 230 | 5 | -0.009 | 2 |
| response model | acct/glm-5p2 | T1-T0 | 233 | 5 | -0.017 | 4 |
| response model | acct/glm-5p2 | T2-T0 | 242 | 5 | -0.038 | 5 |
| response model | acct/glm-5p2 | T3-T0 | 262 | 5 | -0.008 | 3 |
| response model | acct/glm-5p2 | T4-T0 | 230 | 5 | -0.009 | 2 |
| response model | frank/GLM-5.2 | T1-T0 | 391 | 5 | -0.025 | 5 |
| response model | frank/GLM-5.2 | T2-T0 | 389 | 5 | -0.023 | 5 |
| response model | frank/GLM-5.2 | T3-T0 | 408 | 5 | -0.030 | 5 |
| response model | frank/GLM-5.2 | T4-T0 | 373 | 5 | -0.034 | 5 |
| response model | glm-5.2 | T1-T0 | 9 | 5 | 0.067 | 0 |
| response model | glm-5.2 | T2-T0 | 9 | 4 | 0.000 | 0 |
| response model | glm-5.2 | T3-T0 | 12 | 5 | 0.013 | 0 |
| response model | glm-5.2 | T4-T0 | 12 | 5 | 0.089 | 0 |

Provider or transport exceptions were eligible for up to three repository-level adapter invocations per batch with exponential backoff and a 120-second timeout. The batch record's `retry_count` summarizes additional adapter invocations rather than appending each as a separate JSONL row. Each adapter invocation could itself trigger OpenAI-compatible SDK retries; those internal retry events and individual outbound HTTP attempts were not retained. A batch that exhausted its repository-level invocations was written as a technical-error checkpoint and left pending for a later resume invocation. Table @tab:s1-retry-audit therefore reports repository-level terminal checkpoint/resume history and final canonical task state, not a complete HTTP-attempt event log. All 22,500 canonical main tasks ultimately succeeded, while earlier terminal error checkpoints remain preserved. A final row with `retry_count=0` means no additional repository-level adapter invocation occurred in that final batch; it neither erases prior failed resume batches nor proves that the SDK made only one HTTP attempt. Contrary to the protocol's retry-eligibility wording, completed empty or malformed responses were not retried and were evaluated as model outputs; this historical divergence is recorded in `protocol/deviations.md`.

Table: Main-experiment raw checkpoint and resume audit. {#tab:s1-retry-audit}

| System | Raw records | Canonical tasks | Exhausted retry-batch checkpoints | Tasks recovered by resume | Unresolved final tasks |
|---|---|---|---|---|---|
| DeepSeek V4 Flash | 8368 | 7500 | 868 | 868 | 0 |
| GLM-5.2 | 14343 | 7500 | 6843 | 3009 | 0 |
| Kimi K2.7 Code | 15000 | 7500 | 7500 | 7500 | 0 |

Table @tab:s1-revision-task-history reconciles final canonical tasks with the append-only checkpoint history at system-by-condition resolution. A recovered task is a unique task with an earlier terminal technical-error checkpoint and a later successful row; terminal checkpoint-record counts and unique affected-task counts are distinct. All 22,500 final canonical tasks are present and unresolved-task count is zero in every cell.

Table: Canonical main tasks and preserved terminal-checkpoint/resume history by system and condition. {#tab:s1-revision-task-history}

| System | Prompt | Canonical | Prior error tasks | Recovered | Invalid | Empty | First success UTC | Last success UTC |
|---|---|---|---|---|---|---|---|---|
| DeepSeek | Label-only | 1500 | 184 | 184 | 5 | 5 | 2026-07-05 05:33 | 2026-07-06 07:08 |
| DeepSeek | Compact-prose enrichment | 1500 | 158 | 158 | 29 | 28 | 2026-07-05 05:33 | 2026-07-06 07:08 |
| DeepSeek | Bullet-list enrichment | 1500 | 182 | 182 | 22 | 21 | 2026-07-05 05:33 | 2026-07-06 07:08 |
| DeepSeek | Markdown-table enrichment | 1500 | 174 | 174 | 28 | 28 | 2026-07-05 05:33 | 2026-07-06 07:08 |
| DeepSeek | JSON-like-schema enrichment | 1500 | 170 | 170 | 34 | 34 | 2026-07-05 05:33 | 2026-07-06 07:08 |
| GLM | Label-only | 1500 | 604 | 604 | 9 | 6 | 2026-07-06 13:32 | 2026-07-07 09:26 |
| GLM | Compact-prose enrichment | 1500 | 591 | 591 | 13 | 6 | 2026-07-06 13:32 | 2026-07-07 09:26 |
| GLM | Bullet-list enrichment | 1500 | 600 | 600 | 15 | 5 | 2026-07-06 13:31 | 2026-07-07 09:26 |
| GLM | Markdown-table enrichment | 1500 | 600 | 600 | 7 | 4 | 2026-07-06 13:32 | 2026-07-07 09:26 |
| GLM | JSON-like-schema enrichment | 1500 | 614 | 614 | 10 | 6 | 2026-07-06 13:31 | 2026-07-07 09:26 |
| Kimi | Label-only | 1500 | 1500 | 1500 | 0 | 0 | 2026-07-06 07:08 | 2026-07-06 13:31 |
| Kimi | Compact-prose enrichment | 1500 | 1500 | 1500 | 16 | 16 | 2026-07-06 07:08 | 2026-07-06 13:31 |
| Kimi | Bullet-list enrichment | 1500 | 1500 | 1500 | 15 | 15 | 2026-07-06 07:08 | 2026-07-06 13:31 |
| Kimi | Markdown-table enrichment | 1500 | 1500 | 1500 | 20 | 19 | 2026-07-06 07:08 | 2026-07-06 13:31 |
| Kimi | JSON-like-schema enrichment | 1500 | 1500 | 1500 | 21 | 21 | 2026-07-06 07:08 | 2026-07-06 13:31 |

Table @tab:s1-revision-response-models reports every returned provider response-model string by system and condition. The legacy raw field name `model_revision` contains this provider response string; it is not an immutable checkpoint revision.

Table: Provider response-model strings by system and condition. {#tab:s1-revision-response-models}

| System | Prompt | Response model | Tasks | Share |
|---|---|---|---|---|
| DeepSeek | Label-only | ds | 1500 | 100.0% |
| DeepSeek | Compact-prose enrichment | ds | 1500 | 100.0% |
| DeepSeek | Bullet-list enrichment | ds | 1500 | 100.0% |
| DeepSeek | Markdown-table enrichment | ds | 1500 | 100.0% |
| DeepSeek | JSON-like-schema enrichment | ds | 1500 | 100.0% |
| GLM | Label-only | acct/glm-5p2 | 604 | 40.3% |
| GLM | Label-only | frank/GLM-5.2 | 769 | 51.3% |
| GLM | Label-only | glm-5.2 | 127 | 8.5% |
| GLM | Compact-prose enrichment | acct/glm-5p2 | 591 | 39.4% |
| GLM | Compact-prose enrichment | frank/GLM-5.2 | 767 | 51.1% |
| GLM | Compact-prose enrichment | glm-5.2 | 142 | 9.5% |
| GLM | Bullet-list enrichment | acct/glm-5p2 | 600 | 40.0% |
| GLM | Bullet-list enrichment | frank/GLM-5.2 | 758 | 50.5% |
| GLM | Bullet-list enrichment | glm-5.2 | 142 | 9.5% |
| GLM | Markdown-table enrichment | acct/glm-5p2 | 600 | 40.0% |
| GLM | Markdown-table enrichment | frank/GLM-5.2 | 746 | 49.7% |
| GLM | Markdown-table enrichment | glm-5.2 | 154 | 10.3% |
| GLM | JSON-like-schema enrichment | acct/glm-5p2 | 614 | 40.9% |
| GLM | JSON-like-schema enrichment | frank/GLM-5.2 | 760 | 50.7% |
| GLM | JSON-like-schema enrichment | glm-5.2 | 126 | 8.4% |
| Kimi | Label-only | kimi | 1500 | 100.0% |
| Kimi | Compact-prose enrichment | kimi | 1500 | 100.0% |
| Kimi | Bullet-list enrichment | kimi | 1500 | 100.0% |
| Kimi | Markdown-table enrichment | kimi | 1500 | 100.0% |
| Kimi | JSON-like-schema enrichment | kimi | 1500 | 100.0% |

Table @tab:s1-revision-provenance replaces the raw legacy invocation marker with chronological within-system ordinals; it does not expose credentials or infer account identity. Condition shares are descriptive balance checks.

Table: Anonymized invocation-segment balance by system and condition. {#tab:s1-revision-provenance}

| System | Segment | Prompt | Raw records | Prior error tasks | Success in segment | Condition share |
|---|---|---|---|---|---|---|
| DeepSeek | invocation_001 | Label-only | 1500 | 184 | 1316 | 19.8% |
| DeepSeek | invocation_001 | Compact-prose enrichment | 1500 | 158 | 1342 | 20.2% |
| DeepSeek | invocation_001 | Bullet-list enrichment | 1500 | 182 | 1318 | 19.9% |
| DeepSeek | invocation_001 | Markdown-table enrichment | 1500 | 174 | 1326 | 20.0% |
| DeepSeek | invocation_001 | JSON-like-schema enrichment | 1500 | 170 | 1330 | 20.1% |
| DeepSeek | invocation_002 | Label-only | 184 | 0 | 184 | 21.2% |
| DeepSeek | invocation_002 | Compact-prose enrichment | 158 | 0 | 158 | 18.2% |
| DeepSeek | invocation_002 | Bullet-list enrichment | 182 | 0 | 182 | 21.0% |
| DeepSeek | invocation_002 | Markdown-table enrichment | 174 | 0 | 174 | 20.0% |
| DeepSeek | invocation_002 | JSON-like-schema enrichment | 170 | 0 | 170 | 19.6% |
| GLM | invocation_001 | Label-only | 1500 | 604 | 896 | 20.0% |
| GLM | invocation_001 | Compact-prose enrichment | 1500 | 591 | 909 | 20.2% |
| GLM | invocation_001 | Bullet-list enrichment | 1500 | 600 | 900 | 20.0% |
| GLM | invocation_001 | Markdown-table enrichment | 1500 | 600 | 900 | 20.0% |
| GLM | invocation_001 | JSON-like-schema enrichment | 1500 | 614 | 886 | 19.7% |
| GLM | invocation_002 | Label-only | 604 | 604 | 0 | n/a |
| GLM | invocation_002 | Compact-prose enrichment | 591 | 591 | 0 | n/a |
| GLM | invocation_002 | Bullet-list enrichment | 600 | 600 | 0 | n/a |
| GLM | invocation_002 | Markdown-table enrichment | 600 | 600 | 0 | n/a |
| GLM | invocation_002 | JSON-like-schema enrichment | 614 | 614 | 0 | n/a |
| GLM | invocation_003 | Label-only | 157 | 157 | 0 | n/a |
| GLM | invocation_003 | Compact-prose enrichment | 170 | 170 | 0 | n/a |
| GLM | invocation_003 | Bullet-list enrichment | 158 | 158 | 0 | n/a |
| GLM | invocation_003 | Markdown-table enrichment | 164 | 164 | 0 | n/a |
| GLM | invocation_003 | JSON-like-schema enrichment | 176 | 176 | 0 | n/a |
| GLM | invocation_004 | Label-only | 604 | 0 | 604 | 20.1% |
| GLM | invocation_004 | Compact-prose enrichment | 591 | 0 | 591 | 19.6% |
| GLM | invocation_004 | Bullet-list enrichment | 600 | 0 | 600 | 19.9% |
| GLM | invocation_004 | Markdown-table enrichment | 600 | 0 | 600 | 19.9% |
| GLM | invocation_004 | JSON-like-schema enrichment | 614 | 0 | 614 | 20.4% |
| Kimi | invocation_001 | Label-only | 1500 | 1500 | 0 | n/a |
| Kimi | invocation_001 | Compact-prose enrichment | 1500 | 1500 | 0 | n/a |
| Kimi | invocation_001 | Bullet-list enrichment | 1500 | 1500 | 0 | n/a |
| Kimi | invocation_001 | Markdown-table enrichment | 1500 | 1500 | 0 | n/a |
| Kimi | invocation_001 | JSON-like-schema enrichment | 1500 | 1500 | 0 | n/a |
| Kimi | invocation_002 | Label-only | 1500 | 0 | 1500 | 20.0% |
| Kimi | invocation_002 | Compact-prose enrichment | 1500 | 0 | 1500 | 20.0% |
| Kimi | invocation_002 | Bullet-list enrichment | 1500 | 0 | 1500 | 20.0% |
| Kimi | invocation_002 | Markdown-table enrichment | 1500 | 0 | 1500 | 20.0% |
| Kimi | invocation_002 | JSON-like-schema enrichment | 1500 | 0 | 1500 | 20.0% |

Table @tab:s1-revision-access-window applies an objective post-result rule: canonical batch-record start timestamps are assigned to fixed UTC calendar windows [00:00,06:00), [06:00,12:00), [12:00,18:00), or [18:00,24:00). These are not timestamps for individual SDK-internal HTTP attempts, which were unobserved. The table reports condition shares, their deviation from the 20% equal-share reference, exact Macro-F1, and invalid rate. Because issue composition differs between windows and systems were not concurrent, performance columns are descriptive sensitivities only and do not identify a time or routing effect.

Table: Six-hour UTC access-window balance and descriptive performance. {#tab:s1-revision-access-window}

| System | Window start UTC | Prompt | Tasks | Share | vs 20% | Macro-F1 | Invalid |
|---|---|---|---|---|---|---|---|
| DeepSeek | 2026-07-05T00:00 | Label-only | 357 | 19.9% | -0.1 pp | 0.712 | 0.0% |
| DeepSeek | 2026-07-05T00:00 | Compact-prose enrichment | 376 | 20.9% | +0.9 pp | 0.717 | 2.1% |
| DeepSeek | 2026-07-05T00:00 | Bullet-list enrichment | 355 | 19.8% | -0.2 pp | 0.708 | 1.7% |
| DeepSeek | 2026-07-05T00:00 | Markdown-table enrichment | 333 | 18.5% | -1.5 pp | 0.688 | 1.2% |
| DeepSeek | 2026-07-05T00:00 | JSON-like-schema enrichment | 375 | 20.9% | +0.9 pp | 0.668 | 2.1% |
| DeepSeek | 2026-07-05T06:00 | Label-only | 959 | 19.8% | -0.2 pp | 0.699 | 0.4% |
| DeepSeek | 2026-07-05T06:00 | Compact-prose enrichment | 966 | 20.0% | -0.0 pp | 0.686 | 1.7% |
| DeepSeek | 2026-07-05T06:00 | Bullet-list enrichment | 963 | 19.9% | -0.1 pp | 0.693 | 1.3% |
| DeepSeek | 2026-07-05T06:00 | Markdown-table enrichment | 993 | 20.5% | +0.5 pp | 0.681 | 2.3% |
| DeepSeek | 2026-07-05T06:00 | JSON-like-schema enrichment | 955 | 19.7% | -0.3 pp | 0.716 | 2.1% |
| DeepSeek | 2026-07-06T06:00 | Label-only | 184 | 21.2% | +1.2 pp | 0.743 | 0.5% |
| DeepSeek | 2026-07-06T06:00 | Compact-prose enrichment | 158 | 18.2% | -1.8 pp | 0.677 | 3.2% |
| DeepSeek | 2026-07-06T06:00 | Bullet-list enrichment | 182 | 21.0% | +1.0 pp | 0.724 | 1.6% |
| DeepSeek | 2026-07-06T06:00 | Markdown-table enrichment | 174 | 20.0% | +0.0 pp | 0.695 | 0.6% |
| DeepSeek | 2026-07-06T06:00 | JSON-like-schema enrichment | 170 | 19.6% | -0.4 pp | 0.667 | 3.5% |
| GLM | 2026-07-06T12:00 | Label-only | 896 | 20.0% | -0.0 pp | 0.739 | 0.7% |
| GLM | 2026-07-06T12:00 | Compact-prose enrichment | 909 | 20.2% | +0.2 pp | 0.729 | 0.7% |
| GLM | 2026-07-06T12:00 | Bullet-list enrichment | 900 | 20.0% | +0.0 pp | 0.706 | 1.0% |
| GLM | 2026-07-06T12:00 | Markdown-table enrichment | 900 | 20.0% | +0.0 pp | 0.709 | 0.4% |
| GLM | 2026-07-06T12:00 | JSON-like-schema enrichment | 886 | 19.7% | -0.3 pp | 0.709 | 0.7% |
| GLM | 2026-07-07T06:00 | Label-only | 604 | 20.1% | +0.1 pp | 0.734 | 0.5% |
| GLM | 2026-07-07T06:00 | Compact-prose enrichment | 591 | 19.6% | -0.4 pp | 0.695 | 1.2% |
| GLM | 2026-07-07T06:00 | Bullet-list enrichment | 600 | 19.9% | -0.1 pp | 0.726 | 1.0% |
| GLM | 2026-07-07T06:00 | Markdown-table enrichment | 600 | 19.9% | -0.1 pp | 0.714 | 0.5% |
| GLM | 2026-07-07T06:00 | JSON-like-schema enrichment | 614 | 20.4% | +0.4 pp | 0.719 | 0.7% |
| Kimi | 2026-07-06T06:00 | Label-only | 1065 | 19.8% | -0.2 pp | 0.761 | 0.0% |
| Kimi | 2026-07-06T06:00 | Compact-prose enrichment | 1088 | 20.3% | +0.3 pp | 0.728 | 1.3% |
| Kimi | 2026-07-06T06:00 | Bullet-list enrichment | 1066 | 19.9% | -0.1 pp | 0.707 | 0.6% |
| Kimi | 2026-07-06T06:00 | Markdown-table enrichment | 1078 | 20.1% | +0.1 pp | 0.706 | 1.2% |
| Kimi | 2026-07-06T06:00 | JSON-like-schema enrichment | 1072 | 20.0% | -0.0 pp | 0.695 | 1.4% |
| Kimi | 2026-07-06T12:00 | Label-only | 435 | 20.4% | +0.4 pp | 0.752 | 0.0% |
| Kimi | 2026-07-06T12:00 | Compact-prose enrichment | 412 | 19.3% | -0.7 pp | 0.722 | 0.5% |
| Kimi | 2026-07-06T12:00 | Bullet-list enrichment | 434 | 20.4% | +0.4 pp | 0.719 | 2.1% |
| Kimi | 2026-07-06T12:00 | Markdown-table enrichment | 422 | 19.8% | -0.2 pp | 0.699 | 1.7% |
| Kimi | 2026-07-06T12:00 | JSON-like-schema enrichment | 428 | 20.1% | +0.1 pp | 0.720 | 1.4% |

## S1.8 Frozen Taxonomy Prompt Texts

Authoritative sources are `protocol/prompt_registry.yaml` and `results/tables/taxonomy_prompt_texts.csv`. The following code blocks reproduce the frozen taxonomy texts; line wrapping is visual only and no line-wrap indicator characters were included in prompts sent to models.

### Label-only

```text
Allowed labels: bug, feature, question.
```

### Compact-prose enrichment

```text
Allowed labels are bug, feature, and question. A bug reports that existing behavior is incorrect, broken, unexpected, or has regressed relative to intended or previously working behavior. Use bug when the primary intent is to report a malfunction, incorrect result, crash, regression, or deviation from expected existing behavior; do not use it when the issue mainly requests a new capability or asks for explanation or usage help. A feature requests a new capability or a material extension or change to existing intended behavior. Use feature when the primary intent is to add, extend, redesign, or intentionally change functionality or behavior; do not use it when the issue mainly reports broken intended behavior or asks for help. A question primarily asks for explanation, clarification, usage guidance, or help. Use question when the primary intent is to obtain information or assistance; do not use it when the issue mainly asserts that existing behavior is wrong or requests a new or changed capability. Choose the label matching the primary communicative intent. If multiple intents are present, choose the dominant intent. A help-seeking issue that mainly asserts a malfunction is a bug. A request to intentionally change inconvenient but intended behavior is a feature.
```

### Bullet-list enrichment

```text
Allowed labels:

- bug
  - Definition: Reports that existing behavior is incorrect, broken, unexpected, or has regressed relative to intended or previously working behavior.
  - Include when: The primary intent is to report a malfunction, incorrect result, crash, regression, or deviation from expected existing behavior.
  - Exclude when: The primary intent is to request a new capability or to ask for explanation or usage help.

- feature
  - Definition: Requests a new capability or a material extension or change to existing intended behavior.
  - Include when: The primary intent is to add, extend, redesign, or intentionally change functionality or behavior.
  - Exclude when: The issue primarily reports that current intended behavior is broken or primarily asks for help or clarification.

- question
  - Definition: Primarily asks for explanation, clarification, usage guidance, or help.
  - Include when: The primary intent is to obtain information or assistance rather than report a defect or request a capability.
  - Exclude when: The issue primarily asserts that existing behavior is wrong or primarily requests a new or changed capability.

Decision rules:
- Choose the label matching the issue's primary communicative intent.
- If multiple intents are present, choose the dominant intent.
- A help-seeking issue that mainly asserts a malfunction is a bug.
- A request to intentionally change inconvenient but intended behavior is a feature.
```

### Markdown-table enrichment

```text
| Label | Definition | Include when | Exclude when |
|---|---|---|---|
| bug | Reports that existing behavior is incorrect, broken, unexpected, or has regressed relative to intended or previously working behavior. | The primary intent is to report a malfunction, incorrect result, crash, regression, or deviation from expected existing behavior. | The primary intent is to request a new capability or to ask for explanation or usage help. |
| feature | Requests a new capability or a material extension or change to existing intended behavior. | The primary intent is to add, extend, redesign, or intentionally change functionality or behavior. | The issue primarily reports that current intended behavior is broken or primarily asks for help or clarification. |
| question | Primarily asks for explanation, clarification, usage guidance, or help. | The primary intent is to obtain information or assistance rather than report a defect or request a capability. | The issue primarily asserts that existing behavior is wrong or primarily requests a new or changed capability. |

Decision rules:
1. Choose the label matching the issue's primary communicative intent.
2. If multiple intents are present, choose the dominant intent.
3. A help-seeking issue that mainly asserts a malfunction is a bug.
4. A request to intentionally change inconvenient but intended behavior is a feature.
```

### JSON-like-schema enrichment

```text
{
  "labels": {
    "bug": {
      "definition": "Reports that existing behavior is incorrect, broken, unexpected, or has regressed relative to intended or previously working behavior.",
      "include_when": "The primary intent is to report a malfunction, incorrect result, crash, regression, or deviation from expected existing behavior.",
      "exclude_when": "The primary intent is to request a new capability or to ask for explanation or usage help."
    },
    "feature": {
      "definition": "Requests a new capability or a material extension or change to existing intended behavior.",
      "include_when": "The primary intent is to add, extend, redesign, or intentionally change functionality or behavior.",
      "exclude_when": "The issue primarily reports that current intended behavior is broken or primarily asks for help or clarification."
    },
    "question": {
      "definition": "Primarily asks for explanation, clarification, usage guidance, or help.",
      "include_when": "The primary intent is to obtain information or assistance rather than report a defect or request a capability.",
      "exclude_when": "The issue primarily asserts that existing behavior is wrong or primarily requests a new or changed capability."
    }
  },
  "decision_rules": [
    "Choose the label matching the issue's primary communicative intent.",
    "If multiple intents are present, choose the dominant intent.",
    "A help-seeking issue that mainly asserts a malfunction is a bug.",
    "A request to intentionally change inconvenient but intended behavior is a feature."
  ]
}
```

## S1.9 Complete Prompt Templates and API Payload

Table @tab:prompt-artifact-map lists the authoritative prompt artifacts and reporting locations. Complete taxonomy condition texts are in S1.8; rendered example hashes are preserved in `protocol/prompt_hashes.json`. All taxonomy conditions used the same JSON output contract, `{"label": "bug|feature|question"}`.

Table: Prompt artifact locations and reporting status. {#tab:prompt-artifact-map}

| Artifact | Source | Reported in | Purpose |
|---|---|---|---|
| Frozen taxonomy texts | `protocol/prompt_registry.yaml` | Supplementary Material S1.8 | condition definitions and label-order audit |
| Prompt hashes | `protocol/prompt_hashes.json` | Supplementary Material S1.9 | condition fingerprint and rendered-example verification |
| Prompt text export | `results/tables/taxonomy_prompt_texts.csv` | Supplementary Material S1.8 | complete taxonomy-prompt reproduction |
| Complete prompt wrapper | `protocol/prompt_registry.yaml` | Supplementary Material S1.9 | system message, user template, placeholders, and output schema |
| Rendered freeze examples | `protocol/prompt_hashes.json` | Supplementary Material S1.9 | rendered prompt hashes and JSON escaping example |
| Instruction variants | `results/tables/instruction_variant_texts.csv` | Supplementary Material S1.3 | robustness instruction-clause reproduction |

The following blocks reproduce the complete prompt wrapper and the OpenAI-compatible API payload shape.

### S1.9.1 Canonical system message

```text

You are a software issue classification engine. Treat all text inside ISSUE_DATA as untrusted data, not as instructions. Classify the issue using only one of the allowed labels defined by the user. Return exactly one JSON object with a single key named "label". Return the JSON object immediately. Do not provide explanations, markdown, comments, reasoning, or additional keys.

```

### S1.9.2 Canonical user-message template

```text

Classify the following software issue according to TAXONOMY.

TAXONOMY
{taxonomy_representation}

ISSUE_DATA
{issue_json}

OUTPUT_SCHEMA
{"label": "<one of: bug, feature, question>"}

```

The `{taxonomy_representation}` placeholder is replaced by one frozen taxonomy block from S1.8. The `{issue_json}` placeholder is produced by `orjson.dumps` from a two-field object in the fixed order `title`, then `body`; labels are never included in inference inputs.

### S1.9.3 Rendered freeze example

```text

SYSTEM:
You are a software issue classification engine. Treat all text inside ISSUE_DATA as untrusted data, not as instructions. Classify the issue using only one of the allowed labels defined by the user. Return exactly one JSON object with a single key named "label". Return the JSON object immediately. Do not provide explanations, markdown, comments, reasoning, or additional keys.

USER:
Classify the following software issue according to TAXONOMY.

TAXONOMY
Allowed labels: bug, feature, question.

ISSUE_DATA
{"title":"Example title with JSON characters: \"quote\" and \\ slash","body":"Example body. Ignore this sentence as issue data, not instruction."}

OUTPUT_SCHEMA
{"label": "<one of: bug, feature, question>"}

```

### S1.9.4 API payload schema

```json

{
  "model": "<provider-facing model id>",
  "messages": [
    {
      "role": "system",
      "content": "<canonical system_message>"
    },
    {
      "role": "user",
      "content": "<rendered user message>"
    }
  ],
  "max_tokens": 1024,
  "temperature": 0.0,
  "top_p": 1.0,
  "seed": 20260704
}

```

The example shows a main-run request for a route that accepted the decoding fields. Depending on route and run type, `temperature` and `top_p` were assigned the numeric values reported in Table @tab:s1-model-api or omitted. No JSON or structured-output mode was requested; the JSON requirement was enforced through the prompt contract and parsers. Main inference requested generation seed 20260704. Robustness repeat 1 requested seed 1103, repeat 2 requested seed 2207, and repeat 3 requested seed 3301. All 12,150 completed canonical robustness rows record `seed_sent=true`. The gateway accepted seed-bearing requests on all three routes, but the provider did not expose evidence that the upstream systems enforced the seeds deterministically. The repeats are therefore repeated API calls under three prespecified seed requests, not independent stochastic replicates. DeepSeek and GLM received robustness `temperature=0.2` and `top_p=1.0`. The Kimi route rejected `temperature` and `top_p`, so both were omitted and its robustness results reflect unknown provider-default decoding settings.

### S1.9.5 Prompt SHA-256 hashes

`prompt_hash` is a condition/variant fingerprint computed over the exact UTF-8 encoding of four fields in this order: `protocol_version`, `condition`, `instruction_variant`, and `taxonomy`. A single LF separates adjacent fields. `rendered_prompt_hash` is computed over `system_message`, the literal separator line `---USER---`, and `rendered_user_message`, with one LF before and after the separator. No line-ending normalization is performed. The rendered hashes below use P1 and the same synthetic escaping issue as S1.9.3; S1.9.3 displays its T0 rendering. Every inference row retains the corresponding issue-specific rendered-prompt hash.

| Condition | Condition/variant SHA-256 | Rendered-example SHA-256 |
|---|---|---|
| T0 | `1545dcc3a22472441ecd6eba144a00d5753d1b2f034dc1bc7631d7b2e712674f` | `bf1f612f9affc7162e345fc4eba19ea30fc13b0bc0383fa509375208b92bf2ce` |
| T1 | `aa12ed4045216baa81ba3d2716f2da2589f905141be86ca46d42707f805a8233` | `3a82c707cd3e74887ced420989d6b00a6de49d5d38b19d4cb5c30e150471d75f` |
| T2 | `9485ffcc3ee32562d81a51285ee9a9b104fdfbba5681135d42ac3764127f98c5` | `b456dcdd732dc12809a36a265a830bee6228e3c601238c71d45c1eed5042f20b` |
| T3 | `890681541a8a46ac7b92ff9d5afeb80fccf1e5c8355ad7eaf1afa4a67fc51c82` | `a3f1596c69e41b92768baf2f266bd52ef6c20b440f817fda13c4631702a6009e` |
| T4 | `2d2c9f795be2f9334b83db976d4ee4021658574480740a1fe80cc2738bef13a9` | `0166f1e5dccc3f81cd947eee312309516c9f678087631cd17816cccd378b0db3` |

## S1.10 Closest-Study Design Comparison

Table @tab:s1-koyuncu-comparison contrasts the estimands and controlled components of the closest recent study and TAXREP-IRC. It is a design comparison, not a quality ranking; the studies ask different questions.

Table: Design comparison with Koyuncu (2026). {#tab:s1-koyuncu-comparison}

| Dimension | Koyuncu (2026) | TAXREP-IRC |
|---|---|---|
| Task granularity | Fine-grained subtype classification of reports already treated as bugs | Broad issue-type classification: bug, feature, or question |
| Taxonomy size | Nine bug categories | Three issue-type labels |
| Manipulated prompt component | Nine reasoning/prompt instructions and four requested Markdown output-block configurations (C, EC, PC, PEC) | Label names versus one frozen package of definitions, include/exclude criteria, and decision rules; four enriched representations |
| Label-only control | No; every base prompt contains category names and descriptions | Yes; T0 contains only the three label names |
| Output contract | Varied requested Markdown blocks: Category, Explanation plus Category, Process plus Category, or Process plus Explanation plus Category | Fixed exact JSON object with one `label` key across taxonomy conditions |
| Parser/post-processing | Simple category-block regex plus an extended regex sensitivity | Frozen exact JSON parser; frozen lenient parser as sensitivity |
| Models | Six local Q4 Ollama models, 7B--9B, with tags and Ollama commits reported | Three provider-facing aliases through OpenCode Go; immutable backend checkpoint hashes unavailable |
| Paired design | The same 1,024 reports crossed with model, prompt-type, and output-block settings; no description-presence factor | The same issues crossed with all systems and taxonomy conditions; paired repository-by-system contrasts |
| Repeated runs | No repeated call of the same issue-by-model-by-prompt-by-block cell reported | Main matrix single-run; original T0/T2/T4 robustness repeats; completed post-result T0/T3 extension with three new calls per fixed issue-system-condition cell |
| Human-label validation | Targeted author review of agreement/disagreement-selected cases; not blinded multi-expert adjudication | None; benchmark labels are evaluation references rather than independently validated semantic truth |
| Primary contribution | Fine-grained categorization across prompt strategies and output blocks; format adherence, regex recovery, agreement-assisted label review | Marginal benchmark effect of input-side operational taxonomy specification under a fixed output and inference contract |

## S1.11 Targeted T0--T3 Repeat Extension

This section reports the recovery, results, and audit for an extension designed after the main result. It remains a post-result, budget-constrained robustness extension. It uses exactly the pre-existing 150-issue robustness sample, T0 and T3, canonical P1, the three frozen provider-facing systems, and requested seeds 4409, 5501, and 6607. No completed task was repeated during recovery, and no partial targeted result was viewed. The two raw segments were canonicalized to 2,700 unique task keys and frozen by hash before the dedicated targeted analysis performed the first benchmark-label join.

Table @tab:s1-targeted-execution summarizes the stop and missing-task recovery. The first segment remains preserved as an ineligible partial checkpoint in its historical state; scientific eligibility applies only to the completed, frozen two-segment union.

Table: Targeted extension execution and result-freeze audit. {#tab:s1-targeted-execution}

| Audit item | Frozen or observed metadata |
|---|---|
| Scientific status | Post-result, budget-constrained targeted robustness extension; completed through a committed missing-task recovery |
| Planned design | Same 150-issue robustness sample; T0 and T3; P1 only; 3 systems; 3 repeats; requested seeds 4409, 5501, and 6607; 2,700 tasks |
| First segment | Commit `23d0104f2703d1943029080d5ea8c47c01f701ea`; stopped pre-result at `2026-07-12T05:17:59+00:00` with 1,640/2,700 successful tasks; SDK `max_retries=2` was unmetered by the repository ledger |
| Recovery segment | Commit `4cf2056c3cddc81cdb9e5f81a9f990d6c9d57487`; SDK `max_retries=0`; only 1,060 missing keys scheduled; 1,060 completed; no technical error or retry |
| Canonical union | 2,700/2,700 unique successful tasks; 18/18 system-condition-repeat cells contain 150 issues |
| Pre-result freeze | `4cf2056c3cddc81cdb9e5f81a9f990d6c9d57487`; 23 artifacts hashed before targeted gold access |
| Attempt accounting | Historical HTTP attempts not reconstructible: mechanical range 1,643--4,938; recovery reservations 1,063/1,360; conservative combined upper bound 6,001/6,298 |
| Primary result | Repeat-averaged exact T3--T0=-0.015; fixed-repository 95% interval [-0.027, -0.003] |

Table: Full-main, same-sample, and targeted-repeat contrasts. {#tab:s1-targeted-comparison}

| Evidence | Issues | Repeat | T3--T0 |
|---|---|---|---|
| Full main benchmark | 1500 | -- | -0.035 |
| Original main, same 150 issues | 150 | -- | -0.017 |
| New targeted repeat | 150 | 1 | -0.004 |
| New targeted repeat | 150 | 2 | -0.030 |
| New targeted repeat | 150 | 3 | -0.010 |
| New repeat average | 150 | -- | -0.015 |

The full-main contrast and original main execution on the same 150 issues are separate comparators. The smaller same-sample and targeted magnitudes show why sampling composition and repeated execution must not be conflated.

Table: Targeted repeat-averaged system and repository contrasts. {#tab:s1-targeted-directions}

| Scope | Unit | Mean T3--T0 |
|---|---|---|
| System | DeepSeek V4 Flash | -0.013 |
| System | GLM-5.2 | -0.005 |
| System | Kimi K2.7 Code | -0.026 |
| Repository | bitcoin/bitcoin | -0.050 |
| Repository | facebook/react | -0.001 |
| Repository | microsoft/vscode | -0.004 |
| Repository | opencv/opencv | 0.003 |
| Repository | tensorflow/tensorflow | -0.021 |

Table: Targeted system-by-repeat contrasts. {#tab:s1-targeted-system-repeat}

| System | Repeat | T3--T0 |
|---|---|---|
| DeepSeek V4 Flash | 1 | -0.021 |
| DeepSeek V4 Flash | 2 | -0.006 |
| DeepSeek V4 Flash | 3 | -0.010 |
| GLM-5.2 | 1 | 0.008 |
| GLM-5.2 | 2 | -0.025 |
| GLM-5.2 | 3 | 0.001 |
| Kimi K2.7 Code | 1 | 0.001 |
| Kimi K2.7 Code | 2 | -0.058 |
| Kimi K2.7 Code | 3 | -0.020 |

All three repeat averages and system averages were negative; four of five repository averages and six of nine system-by-repeat averages were negative. This is directional targeted support, not uniform cell-level reproduction.

Table: Targeted parsing sensitivities. {#tab:s1-targeted-parsing}

| Parsing analysis | Repeat-averaged T3--T0 | Minimum cell n |
|---|---|---|
| Exact contract | -0.015 | 30 |
| Lenient | -0.015 | 30 |
| Exact both-valid | -0.015 | 28 |

Table: Targeted exact-output compliance. {#tab:s1-targeted-invalid}

| Prompt | Responses | Invalid | Empty | Invalid rate |
|---|---|---|---|---|
| Label-only | 1350 | 0 | 0 | 0.0% |
| Markdown-table enrichment | 1350 | 12 | 11 | 0.9% |

Exact, lenient, and exact-both-valid contrasts were similar. T0 produced no exact invalid output, whereas T3 produced 12/1,350; the both-valid result remained negative, so parsing failure alone does not account for the contrast. Conditioning on both-valid output remains a post-treatment sensitivity rather than a causal decomposition.

Table: Targeted within-condition repeat agreement; invalid output is a fourth nominal state. {#tab:s1-targeted-agreement}

| Prompt | Scope | Flip | Stability | Unanimous | Alpha |
|---|---|---|---|---|---|
| Label-only | All systems | 2.8% | 97.2% | 95.8% | 0.954 |
| Label-only | DeepSeek V4 Flash | 3.6% | 96.4% | 94.7% | 0.941 |
| Label-only | GLM-5.2 | 1.3% | 98.7% | 98.0% | 0.978 |
| Label-only | Kimi K2.7 Code | 3.6% | 96.4% | 94.7% | 0.943 |
| Markdown-table enrichment | All systems | 3.9% | 96.1% | 94.7% | 0.935 |
| Markdown-table enrichment | DeepSeek V4 Flash | 4.4% | 95.6% | 94.0% | 0.926 |
| Markdown-table enrichment | GLM-5.2 | 1.8% | 98.2% | 97.3% | 0.970 |
| Markdown-table enrichment | Kimi K2.7 Code | 5.6% | 94.4% | 92.7% | 0.908 |

Repeat calls are not independent replicates. The agreement table treats invalid output as a fourth nominal state and reports prediction stability as one minus mean pairwise flip rate.

Table: Targeted access-window and condition provenance. {#tab:s1-targeted-provenance}

| Segment | System | Prompt | Tasks | Invalid | First UTC | Last UTC |
|---|---|---|---|---|---|---|
| Window 1 (stopped segment) | DeepSeek V4 Flash | Label-only | 271 | 0 | 2026-07-12T04:46:57+00:00 | 2026-07-12T05:13:52+00:00 |
| Window 1 (stopped segment) | DeepSeek V4 Flash | Markdown-table enrichment | 256 | 1 | 2026-07-12T04:47:01+00:00 | 2026-07-12T05:14:00+00:00 |
| Window 1 (stopped segment) | GLM-5.2 | Label-only | 274 | 0 | 2026-07-12T04:46:57+00:00 | 2026-07-12T05:13:54+00:00 |
| Window 1 (stopped segment) | GLM-5.2 | Markdown-table enrichment | 284 | 1 | 2026-07-12T04:47:01+00:00 | 2026-07-12T05:13:45+00:00 |
| Window 1 (stopped segment) | Kimi K2.7 Code | Label-only | 265 | 0 | 2026-07-12T04:47:00+00:00 | 2026-07-12T05:13:58+00:00 |
| Window 1 (stopped segment) | Kimi K2.7 Code | Markdown-table enrichment | 290 | 6 | 2026-07-12T04:46:57+00:00 | 2026-07-12T05:14:12+00:00 |
| Window 2 (metered recovery) | DeepSeek V4 Flash | Label-only | 179 | 0 | 2026-07-12T21:02:28+00:00 | 2026-07-12T21:21:43+00:00 |
| Window 2 (metered recovery) | DeepSeek V4 Flash | Markdown-table enrichment | 194 | 3 | 2026-07-12T21:02:17+00:00 | 2026-07-12T21:21:41+00:00 |
| Window 2 (metered recovery) | GLM-5.2 | Label-only | 176 | 0 | 2026-07-12T21:02:15+00:00 | 2026-07-12T21:21:44+00:00 |
| Window 2 (metered recovery) | GLM-5.2 | Markdown-table enrichment | 166 | 0 | 2026-07-12T21:02:22+00:00 | 2026-07-12T21:21:46+00:00 |
| Window 2 (metered recovery) | Kimi K2.7 Code | Label-only | 185 | 0 | 2026-07-12T21:02:15+00:00 | 2026-07-12T21:21:57+00:00 |
| Window 2 (metered recovery) | Kimi K2.7 Code | Markdown-table enrichment | 160 | 1 | 2026-07-12T21:02:15+00:00 | 2026-07-12T21:21:54+00:00 |

The access-window split follows execution recovery rather than performance. T0 and T3 appear in both segments for every system, but exact separation of provider time, route, and issue-composition effects is impossible; the segment table is descriptive provenance only.

Table: Targeted segment-level completion-call accounting. {#tab:s1-targeted-budget}

| Ledger segment | Cap | Used | Health | Inference | Retry | Reserved/no row | Reconciled |
|---|---|---|---|---|---|---|---|
| recovery access window 2 | 1360 | 1063 | 3 | 1060 | 0 | 0 | true |
| stopped access window 1 | 3000 | 1646 | 3 | 1643 | 0 | 3 | true |

The three unmatched historical inference reservations were in flight when the first process was stopped. The audit treats exactly those reservations as conservative overcount; all 1,060 recovery inference ordinals match raw terminal records. No unused reserve authorized another experiment.

### S1.11.1 Frozen Identifiers and SHA-256 Values

- Original protocol file: `protocol/targeted_t3_repeat_extension.md`
- Original protocol commit: `ef660c6cb925ebdba4e5f2ebea40fe1bca85db9c`
- Original protocol Markdown SHA-256: `fc4c878cf6e5e3ad9431e6a89bc70b7856e90f061f4ebe99d18aadd22d55a070`
- Original config SHA-256: `2b1610a17c49a8beff5debef6829b429094652b4762b1057ea2647b00bc323f1`
- Recovery protocol file: `protocol/targeted_t3_repeat_recovery.md`
- Recovery protocol commit: `38171a8`
- Recovery protocol Markdown SHA-256: `10a6560d05a92b6f5ca25c401091b1d4651b55a3de15208e5e6ab9cc247c7807`
- Recovery config SHA-256: `56c7e03998a8aa16f3a3e40155d66401d0d2cbb61eaa2fbb3506d5ec9164ddb8`
- Prompt-registry SHA-256: `61240c10ad4e9025ee99a3c1a78244ad77ef3676867d6af242efe35f967edb64`
- T0 prompt SHA-256: `1545dcc3a22472441ecd6eba144a00d5753d1b2f034dc1bc7631d7b2e712674f`
- T3 prompt SHA-256: `890681541a8a46ac7b92ff9d5afeb80fccf1e5c8355ad7eaf1afa4a67fc51c82`
- Original/recovery task-order SHA-256: `45b188787afc4cd9412a78c5c1cf74ab3b0f1646b82561a0a8cd8b6d97d43d34`

### S1.11.2 Exact Commands and Preserved Artifacts

```text
uv run taxrep targeted verify-freeze
uv run taxrep targeted preflight
scripts/tmux/start_targeted_t3_repeat.sh
uv run taxrep infer --config protocol/targeted_t3_repeat_extension.yaml
uv run taxrep targeted recovery-catalog
uv run taxrep targeted freeze-recovery --protocol-commit 38171a8
uv run taxrep targeted verify-recovery-freeze
uv run taxrep targeted recovery-preflight
scripts/tmux/start_targeted_t3_repeat_recovery.sh
uv run taxrep infer --config protocol/targeted_t3_repeat_recovery.yaml
uv run taxrep reports run targeted-t3-repeat
uv run taxrep reports completeness targeted-t3-repeat
uv run python scripts/freeze_targeted_results.py --frozen-by author-authorized-recovery
uv run taxrep targeted analyze
uv run taxrep targeted audit
```

Preserved inputs include both append-only JSONL files and Parquet checkpoints, the canonical label-free 2,700-row Parquet union, original and recovery manifests, preflights, provider snapshots, ledgers, tmux logs, protocol/hash manifests, the result freeze, all targeted CSV tables, and both targeted statistics JSON files. The replication package excludes API keys and local environment files.
