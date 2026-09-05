from .cloudbackup import (
    CloudBackup,
    CloudBackupError,
)


def main() -> None:

    print("=== AM3 Backup Auto ===")
    print()

    try:

        cloudbackup = CloudBackup()

        print(
            f"CloudBackupPRO: "
            f"{cloudbackup.app_home}"
        )

        print(
            f"Setting Home:   "
            f"{cloudbackup.setting_home}"
        )

        print()
        print("Backup Sets encontrados:")
        print()

        backup_sets = cloudbackup.list_backup_sets()

        for backup_set in backup_sets:

            print(
                f"- {backup_set.name} "
                f"(ID: {backup_set.id})"
            )

        print()
        print(
            f"Total de Backup Sets: "
            f"{len(backup_sets)}"
        )

    except CloudBackupError as exc:

        print()
        print("ERRO:")
        print(exc)


if __name__ == "__main__":
    main()