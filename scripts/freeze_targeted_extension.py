from __future__ import annotations

import argparse

from taxrep.targeted import freeze_targeted_extension


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze the post-result targeted T0-T3 extension artifacts."
    )
    parser.add_argument("--protocol-commit", default=None)
    args = parser.parse_args()
    payload = freeze_targeted_extension(protocol_commit=args.protocol_commit)
    print(
        {
            "hash_manifest": "experiment/targeted_t3_repeat_extension_hashes.json",
            "protocol_commit": payload["protocol_commit"],
            "task_count": payload["task_plan"]["task_count"],
            "task_order_sha256": payload["task_plan"]["task_order_sha256"],
        }
    )


if __name__ == "__main__":
    main()
