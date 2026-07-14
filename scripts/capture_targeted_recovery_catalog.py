from __future__ import annotations

from taxrep.targeted_recovery import capture_targeted_recovery_catalog


def main() -> None:
    result = capture_targeted_recovery_catalog()
    print(
        {
            "path": result["path"],
            "sha256": result["sha256"],
            "model_ids_present": result["model_ids_present"],
            "existing_immutable_snapshot": result["existing_immutable_snapshot"],
        }
    )


if __name__ == "__main__":
    main()
