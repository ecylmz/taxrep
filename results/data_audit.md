# Data Audit

- Validated at UTC: `2026-07-14T08:10:50+00:00`
- Source commit: `2927bc67eb42db8affd16eaf3e5a6d74f3063961`
- Errors: `0`
- Warnings: `0`


## Train Split

- Rows: `1500`
- Columns: `repo, created_at, label, title, body`
- Repositories: `{'bitcoin/bitcoin': 300, 'facebook/react': 300, 'microsoft/vscode': 300, 'opencv/opencv': 300, 'tensorflow/tensorflow': 300}`
- Labels: `{'bug': 500, 'feature': 500, 'question': 500}`
- Missing titles: `0`
- Missing or empty bodies: `0`
- Exact normalized duplicate count: `1`
- Conflicting label same-text count: `0`
- Text length chars: `{'min': 3, 'median': 1159.0, 'p95': 5797.149999999998, 'max': 207857}`
- Prompt-injection-like records: `0`

## Test Split

- Rows: `1500`
- Columns: `repo, created_at, label, title, body`
- Repositories: `{'bitcoin/bitcoin': 300, 'facebook/react': 300, 'microsoft/vscode': 300, 'opencv/opencv': 300, 'tensorflow/tensorflow': 300}`
- Labels: `{'bug': 500, 'feature': 500, 'question': 500}`
- Missing titles: `0`
- Missing or empty bodies: `2`
- Exact normalized duplicate count: `1`
- Conflicting label same-text count: `0`
- Text length chars: `{'min': 3, 'median': 1182.0, 'p95': 6322.05, 'max': 61681}`
- Prompt-injection-like records: `0`

## Cross Split

- Normalized exact duplicate texts: `3`
- Train rows in overlap: `4`
- Test rows in overlap: `3`
