# TAXREP Experiment Code and Results

This repository contains the public experiment code and result artifacts for
the article **A Paired Fixed-Benchmark Study of Operational Taxonomy Enrichment for LLM-Based Issue Classification**.

Repository: <https://github.com/ecylmz/taxrep>

The public tree includes the code used for provider API calls, checkpointed
inference, parsing, evaluation, statistical analysis, targeted-run auditing,
and figure generation. It also includes the completed experimental results.
Manuscript sources and generation code, revision notes, and narrative protocol
documents are intentionally excluded.

## Repository map

| Material | Location |
|---|---|
| Python experiment and analysis package | `src/taxrep/` |
| Frozen run configurations | `configs/` |
| Machine-readable prompt, model, provider, and targeted-run records | `experiment/` |
| Inference and analysis launchers | `scripts/` |
| Locked Python 3.12 environment | `pyproject.toml`, `uv.lock`, `.python-version` |
| Append-only raw model responses | `results/raw_predictions/` |
| Canonical parsed predictions | `results/parsed_predictions/` |
| Classification and selection metrics | `results/metrics/` |
| Statistical outputs | `results/statistics/` |
| Result tables and forensic audit tables | `results/tables/`, `results/full_tables/` |
| Rendered result figures | `results/figures/` |
| Run, completion, freeze, and call-budget records | `results/run_manifests/` |
| Preserved targeted-run execution logs | `results/logs/` |

Raw model outputs have not been overwritten or silently corrected.
`PUBLIC_REDACTION_PROVENANCE.json` enumerates the small set of operational
records in which a local absolute filesystem path was normalized for public
release; scientific fields and raw prediction artifacts were not changed.

## Environment setup

```bash
uv sync --frozen
uv run taxrep data download
uv run taxrep data validate
```

The upstream dataset is downloaded locally and is ignored by Git. Provider
credentials are not included and must never be committed. Inspecting the
archived results does not require credentials or new API calls.

## Inference code

The provider adapter used for experimental classifications is
`src/taxrep/providers/opencode_go.py`. The main entry points are:

```bash
uv run taxrep pilot --config configs/pilot.yaml
uv run taxrep infer --config configs/train_selection.yaml
uv run taxrep infer --config configs/main.yaml
uv run taxrep infer --config configs/robustness.yaml
```

Long jobs have versioned launchers under `scripts/tmux/`. Running inference
again is not necessary to inspect or analyze the published outputs and may
incur provider charges.

## Rebuild analyses from archived responses

After reconstructing the local upstream data, the non-inference analysis chain
is:

```bash
uv run taxrep parse
uv run taxrep evaluate
uv run taxrep held-out
uv run taxrep statistics
uv run taxrep targeted analyze
uv run taxrep targeted audit
uv run taxrep figures
```

`scripts/tmux/start_analysis.sh` runs the same chain in a detached session.

## Integrity

`MANIFEST.sha256` authenticates every public file:

```bash
shasum -a 256 -c MANIFEST.sha256
```

`ARTIFACT_INVENTORY.json` provides file-level categories, sizes, and hashes.
`GITHUB_DIRECTORY_VERIFICATION.json` records the public-tree security and size
checks. The immutable code-and-results snapshot commit is recorded after the
history rewrite in this README and `SOURCE_SNAPSHOT.json`.

## Data and publication boundary

The upstream NLBSE 2024 CSV files and derived issue-text/gold-label data are
not redistributed because the audited upstream commit supplies no explicit
non-empty redistribution license. See `THIRD_PARTY_NOTICES.md` for the pinned
upstream identity and checksums.

The repository does not contain `paper/`, `revision/`, or `protocol/`
directories. Machine-readable experiment inputs needed by the code are kept
under `experiment/`; manuscript and manuscript-generation assets are not part
of this public repository.

## Citation and license

Citation metadata is in `CITATION.cff`. Project-authored code and documentation
are MIT-licensed. Third-party data remains subject to its own terms and is not
redistributed here.
