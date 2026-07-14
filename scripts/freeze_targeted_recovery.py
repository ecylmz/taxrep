from __future__ import annotations

import argparse

from taxrep.targeted_recovery import freeze_targeted_recovery


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze the missing-task recovery before any recovery completion call."
    )
    parser.add_argument("--protocol-commit", required=True)
    args = parser.parse_args()
    result = freeze_targeted_recovery(protocol_commit=args.protocol_commit)
    print(
        {
            "protocol_commit": result["protocol_commit"],
            "prior_successful_tasks": result["reconciliation"][
                "prior_successful_tasks"
            ],
            "missing_tasks": result["reconciliation"]["missing_tasks"],
            "revision_http_attempt_hard_cap": result["budget"][
                "revision_http_attempt_hard_cap"
            ],
        }
    )


if __name__ == "__main__":
    main()
