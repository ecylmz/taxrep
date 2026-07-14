# Third-Party Notices

The root MIT license applies only to project-authored archive metadata and
documentation. It does not grant rights in third-party materials.

## NLBSE 2024 issue-report classification data

The study used data from
<https://github.com/nlbse2024/issue-report-classification> at commit
`2927bc67eb42db8affd16eaf3e5a6d74f3063961`. At that commit, the upstream
`LICENSE` file is zero bytes and supplies no explicit redistribution grant.
This public results archive therefore omits upstream CSV files and derived
issue-text or gold-label files.

Pinned upstream files used locally during the study:

| Split | Source path | Bytes | SHA-256 |
|---|---|---:|---|
| Train | `data/issues_train.csv` | 3,680,400 | `18dc42a30aa33dccadb723ad3baeb164d38bff521496f985ca2791c26b8939f5` |
| Test | `data/issues_test.csv` | 3,449,390 | `4f7d8619d4e5adbea126e548fd8c214449288f3a93bb3bc130c54cd307af7e85` |

The raw model responses and derived result artifacts in `results/` are study
outputs, not redistributed copies of the upstream issue dataset. The code can
reconstruct local inputs from the pinned upstream source, but those local files
remain excluded from Git.
