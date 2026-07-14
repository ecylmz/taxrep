from __future__ import annotations

import pandas as pd

from taxrep.constants import PROJECT_ROOT


def build_figures() -> dict[str, str]:
    import matplotlib.pyplot as plt

    block_path = PROJECT_ROOT / "results" / "tables" / "block_metrics.csv"
    if not block_path.exists():
        raise FileNotFoundError("Run `taxrep statistics` before generating figures")
    frame = pd.read_csv(block_path)
    rank_frame = frame.copy()
    rank_frame["rank"] = rank_frame.groupby(["model_id", "repository"])["macro_f1"].rank(
        ascending=False,
        method="min",
    )
    heat = rank_frame.pivot_table(
        index=["model_id", "repository"],
        columns="taxonomy_condition",
        values="rank",
        aggfunc="first",
    )
    fig, ax = plt.subplots(figsize=(7, 5))
    image = ax.imshow(heat.to_numpy(), aspect="auto", cmap="viridis_r")
    ax.set_xticks(range(len(heat.columns)), heat.columns)
    ax.set_yticks(range(len(heat.index)), [f"{m}\n{r}" for m, r in heat.index])
    ax.set_title("Taxonomy-condition ranks across model-project blocks")
    fig.colorbar(image, ax=ax, label="Rank")
    fig.tight_layout()
    out = PROJECT_ROOT / "results" / "figures" / "condition_rank_heatmap.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return {"condition_rank_heatmap": str(out)}
