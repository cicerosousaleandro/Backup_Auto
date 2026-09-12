from __future__ import annotations

import logging
import time
from pathlib import Path

from .cloudbackup import CloudBackup, CloudBackupError


STARTUP_DELAY = 30
LOG_DIRECTORY = Path(__file__).resolve().parents[2] / "logs"


def configure_logging() -> None:
    LOG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_file = LOG_DIRECTORY / "backup_auto.log"

    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8",
    )


def main() -> None:
    configure_logging()

    logger = logging.getLogger("backup_auto")

    logger.info("==================================================")
    logger.info("Backup_Auto iniciado.")
    logger.info("==================================================")

    try:
        logger.info(
            "Aguardando %s segundos para estabilização do Windows.",
            STARTUP_DELAY,
        )

        time.sleep(STARTUP_DELAY)

        cloudbackup = CloudBackup()

        logger.info(
            "CloudBackupPRO encontrado: %s",
            cloudbackup.app_home,
        )

        logger.info(
            "Setting Home encontrado: %s",
            cloudbackup.setting_home,
        )

        backup_sets = cloudbackup.list_backup_sets()

        logger.info(
            "Backup Sets encontrados: %d",
            len(backup_sets),
        )

        if not backup_sets:
            logger.warning("Nenhum Backup Set encontrado.")
            return

        for index, backup_set in enumerate(
            backup_sets,
            start=1,
        ):
            logger.info(
                "Backup Set %d/%d: %s [%s]",
                index,
                len(backup_sets),
                backup_set.name,
                backup_set.id,
            )

        success_count = 0
        failure_count = 0

        for index, backup_set in enumerate(
            backup_sets,
            start=1,
        ):
            logger.info(
                "--------------------------------------------------"
            )

            logger.info(
                "Iniciando Backup Set %d/%d: %s [%s]",
                index,
                len(backup_sets),
                backup_set.name,
                backup_set.id,
            )

            try:
                result = cloudbackup.run_backup(
                    backup_set
                )

                if result.success:
                    success_count += 1

                    logger.info(
                        "Backup Set concluído com sucesso: "
                        "%s [%s]",
                        backup_set.name,
                        backup_set.id,
                    )

                else:
                    failure_count += 1

                    logger.error(
                        "Backup Set não confirmou sucesso: "
                        "%s [%s]",
                        backup_set.name,
                        backup_set.id,
                    )

                if result.output:
                    logger.info(
                        "Saída do Backup Set %s:\n%s",
                        backup_set.id,
                        result.output,
                    )

            except CloudBackupError as exc:
                failure_count += 1

                logger.exception(
                    "Erro ao executar Backup Set "
                    "%s [%s]: %s",
                    backup_set.name,
                    backup_set.id,
                    exc,
                )

            except Exception as exc:
                failure_count += 1

                logger.exception(
                    "Erro inesperado no Backup Set "
                    "%s [%s]: %s",
                    backup_set.name,
                    backup_set.id,
                    exc,
                )

        logger.info(
            "=================================================="
        )

        logger.info(
            "Processamento dos Backup Sets concluído."
        )

        logger.info(
            "Total: %d | Sucesso: %d | Falhas: %d",
            len(backup_sets),
            success_count,
            failure_count,
        )

        logger.info(
            "=================================================="
        )

    except CloudBackupError as exc:
        logger.exception(
            "Erro durante a execução do Backup_Auto: %s",
            exc,
        )

    except Exception as exc:
        logger.exception(
            "Erro inesperado no Backup_Auto: %s",
            exc,
        )


if __name__ == "__main__":
    main()