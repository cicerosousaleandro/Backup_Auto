from __future__ import annotations

import json
import logging
import os
import sys
import time
import winreg
from pathlib import Path

from .cloudbackup import BackupSet, CloudBackup, CloudBackupError


DEFAULT_STARTUP_DELAY = 30
PROGRAM_DATA_DIRECTORY = Path(
    os.environ.get("PROGRAMDATA", r"C:\ProgramData")
)
PRODUCTION_DIRECTORY = PROGRAM_DATA_DIRECTORY / "Backup_Auto"

STARTUP_REGISTRY_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Run"
)
STARTUP_REGISTRY_VALUE = "Backup_Auto"


def get_base_directory() -> Path:
    if getattr(sys, "frozen", False):
        return PRODUCTION_DIRECTORY

    return Path(__file__).resolve().parents[2]


BASE_DIRECTORY = get_base_directory()
CONFIG_FILE = BASE_DIRECTORY / "config.json"
LOG_DIRECTORY = BASE_DIRECTORY / "logs"


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


def register_startup() -> None:
    if not getattr(sys, "frozen", False):
        logging.getLogger("backup_auto").info(
            "Modo de desenvolvimento: inicialização automática "
            "não registrada."
        )
        return

    executable_path = Path(sys.executable).resolve()

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REGISTRY_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(
                key,
                STARTUP_REGISTRY_VALUE,
                0,
                winreg.REG_SZ,
                f'"{executable_path}"',
            )

    except OSError as exc:
        raise CloudBackupError(
            "Não foi possível registrar o Backup_Auto "
            f"para inicialização automática: {exc}"
        ) from exc

    logging.getLogger("backup_auto").info(
        "Inicialização automática registrada: %s",
        executable_path,
    )


def unregister_startup() -> None:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            STARTUP_REGISTRY_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            try:
                winreg.DeleteValue(
                    key,
                    STARTUP_REGISTRY_VALUE,
                )
            except FileNotFoundError:
                pass

    except FileNotFoundError:
        pass

    except OSError as exc:
        logging.getLogger("backup_auto").warning(
            "Não foi possível remover o registro de inicialização: %s",
            exc,
        )


def load_config() -> tuple[int, list[BackupSet]]:
    if not CONFIG_FILE.exists():
        raise CloudBackupError(
            f"Arquivo de configuração não encontrado: {CONFIG_FILE}"
        )

    try:
        with CONFIG_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = json.load(file)

    except json.JSONDecodeError as exc:
        raise CloudBackupError(
            f"Arquivo de configuração inválido: {CONFIG_FILE}"
        ) from exc

    startup_delay = config.get(
        "startup_delay",
        DEFAULT_STARTUP_DELAY,
    )

    try:
        startup_delay = int(startup_delay)

    except (TypeError, ValueError) as exc:
        raise CloudBackupError(
            "O campo 'startup_delay' deve ser um número inteiro."
        ) from exc

    if startup_delay < 0:
        raise CloudBackupError(
            "O campo 'startup_delay' não pode ser negativo."
        )

    configured_sets = config.get(
        "backup_sets",
        [],
    )

    if not isinstance(configured_sets, list):
        raise CloudBackupError(
            "O campo 'backup_sets' deve ser uma lista."
        )

    backup_sets: list[BackupSet] = []
    ids_seen: set[str] = set()

    for index, item in enumerate(
        configured_sets,
        start=1,
    ):
        if not isinstance(item, dict):
            raise CloudBackupError(
                f"Backup Set na posição {index} possui formato inválido."
            )

        backup_set_id = str(
            item.get("id", "")
        ).strip()

        backup_set_name = str(
            item.get("name", "")
        ).strip()

        if not backup_set_id:
            raise CloudBackupError(
                f"Backup Set na posição {index} não possui ID."
            )

        if backup_set_id in ids_seen:
            raise CloudBackupError(
                f"Backup Set duplicado na configuração: "
                f"{backup_set_id}"
            )

        ids_seen.add(backup_set_id)

        if not backup_set_name:
            backup_set_name = (
                f"Backup Set {backup_set_id}"
            )

        backup_sets.append(
            BackupSet(
                name=backup_set_name,
                id=backup_set_id,
            )
        )

    return startup_delay, backup_sets


def configure_client() -> int:
    logger = logging.getLogger("backup_auto")

    logger.info("==================================================")
    logger.info(
        "Iniciando configuração automática do Backup_Auto."
    )
    logger.info(
        "Diretório base: %s",
        BASE_DIRECTORY,
    )
    logger.info(
        "Arquivo de configuração: %s",
        CONFIG_FILE,
    )
    logger.info("==================================================")

    try:
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

        if not backup_sets:
            raise CloudBackupError(
                "Nenhum Backup Set foi encontrado "
                "no CloudBackupPRO."
            )

        config = {
            "startup_delay": DEFAULT_STARTUP_DELAY,
            "backup_sets": [
                {
                    "name": backup_set.name,
                    "id": backup_set.id,
                }
                for backup_set in backup_sets
            ],
        }

        CONFIG_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_file = CONFIG_FILE.with_suffix(
            ".tmp"
        )

        with temporary_file.open(
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                config,
                file,
                ensure_ascii=False,
                indent=4,
            )
            file.write("\n")

        temporary_file.replace(
            CONFIG_FILE
        )

        logger.info(
            "Configuração criada com sucesso: %s",
            CONFIG_FILE,
        )

        logger.info(
            "Backup Sets encontrados: %d",
            len(backup_sets),
        )

        for index, backup_set in enumerate(
            backup_sets,
            start=1,
        ):
            logger.info(
                "Backup Set %d: %s [%s]",
                index,
                backup_set.name,
                backup_set.id,
            )

        register_startup()

        logger.info(
            "Configuração automática concluída."
        )

        logger.info("==================================================")

        return 0

    except CloudBackupError as exc:
        logger.exception(
            "Falha na configuração automática: %s",
            exc,
        )
        return 1

    except Exception as exc:
        logger.exception(
            "Erro inesperado durante a configuração automática: %s",
            exc,
        )
        return 2


def run_backup_auto() -> int:
    logger = logging.getLogger("backup_auto")

    logger.info("==================================================")
    logger.info(
        "Backup_Auto iniciado."
    )
    logger.info(
        "Diretório base: %s",
        BASE_DIRECTORY,
    )
    logger.info(
        "Arquivo de configuração: %s",
        CONFIG_FILE,
    )
    logger.info("==================================================")

    try:
        startup_delay, backup_sets = load_config()

        logger.info(
            "Tempo de espera configurado: %s segundos.",
            startup_delay,
        )

        logger.info(
            "Backup Sets configurados: %d",
            len(backup_sets),
        )

        if not backup_sets:
            logger.warning(
                "Nenhum Backup Set configurado."
            )
            return 0

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

        if startup_delay > 0:
            logger.info(
                "Aguardando %s segundos para "
                "estabilização do Windows.",
                startup_delay,
            )

            time.sleep(startup_delay)

        cloudbackup = CloudBackup()

        logger.info(
            "CloudBackupPRO encontrado: %s",
            cloudbackup.app_home,
        )

        logger.info(
            "Setting Home encontrado: %s",
            cloudbackup.setting_home,
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
                    "Erro ao executar Backup Set %s [%s]: %s",
                    backup_set.name,
                    backup_set.id,
                    exc,
                )

            except Exception as exc:
                failure_count += 1

                logger.exception(
                    "Erro inesperado no Backup Set %s [%s]: %s",
                    backup_set.name,
                    backup_set.id,
                    exc,
                )

        logger.info("==================================================")

        logger.info(
            "Processamento dos Backup Sets concluído."
        )

        logger.info(
            "Total: %d | Sucesso: %d | Falhas: %d",
            len(backup_sets),
            success_count,
            failure_count,
        )

        logger.info("==================================================")

        return 0 if failure_count == 0 else 1

    except CloudBackupError as exc:
        logger.exception(
            "Erro durante a execução do Backup_Auto: %s",
            exc,
        )
        return 1

    except Exception as exc:
        logger.exception(
            "Erro inesperado no Backup_Auto: %s",
            exc,
        )
        return 2


def main() -> int:
    configure_logging()

    arguments = sys.argv[1:]

    if "--configure" in arguments:
        return configure_client()

    if "--remove-startup" in arguments:
        unregister_startup()
        return 0

    return run_backup_auto()


if __name__ == "__main__":
    sys.exit(main())