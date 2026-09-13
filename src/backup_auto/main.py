from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

from .cloudbackup import BackupSet, CloudBackup, CloudBackupError


APP_NAME = "Backup_Auto"
STARTUP_SCRIPT_NAME = "Backup_Auto_Start.vbs"
DEFAULT_STARTUP_DELAY = 30


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[2]


BASE_DIR = get_base_dir()
CONFIG_FILE = BASE_DIR / "config.json"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "backup_auto.log"


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        encoding="utf-8",
    )


logger = logging.getLogger(APP_NAME)


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise RuntimeError(
            f"Arquivo de configuração não encontrado: {CONFIG_FILE}"
        )

    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_config(config: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with CONFIG_FILE.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=4)


def get_startup_folder() -> Path:
    app_data = os.environ.get("APPDATA")

    if not app_data:
        raise RuntimeError(
            "A variável APPDATA não está disponível."
        )

    startup = (
        Path(app_data)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )

    startup.mkdir(parents=True, exist_ok=True)

    return startup


def get_startup_script() -> Path:
    return get_startup_folder() / STARTUP_SCRIPT_NAME


def register_startup() -> None:
    if not getattr(sys, "frozen", False):
        logger.info(
            "Registro da inicialização ignorado em modo de desenvolvimento."
        )
        return

    startup_folder = get_startup_folder()
    startup_script = get_startup_script()
    executable = Path(sys.executable).resolve()

    script_content = (
        'Set shell = CreateObject("WScript.Shell")\r\n'
        f'shell.Run Chr(34) & "{executable}" & Chr(34), 0, False\r\n'
        'Set shell = Nothing\r\n'
    )

    try:
        startup_script.write_text(
            script_content,
            encoding="utf-8",
        )

        for old_file in (
            startup_folder / "Backup_Auto.lnk",
            startup_folder / "Backup_Auto_Start.cmd",
        ):
            if old_file.exists():
                old_file.unlink()

    except OSError as exc:
        raise RuntimeError(
            f"Não foi possível configurar a inicialização automática: {exc}"
        ) from exc

    logger.info(
        "Inicialização automática configurada: %s",
        startup_script,
    )


def unregister_startup() -> None:
    startup_folder = get_startup_folder()

    for file in (
        startup_folder / STARTUP_SCRIPT_NAME,
        startup_folder / "Backup_Auto.lnk",
        startup_folder / "Backup_Auto_Start.cmd",
    ):
        if file.exists():
            file.unlink()

            logger.info(
                "Inicialização automática removida: %s",
                file,
            )


def create_configuration() -> dict:
    logger.info("Criando configuração inicial do Backup_Auto.")

    cloudbackup = CloudBackup()
    backup_sets = cloudbackup.list_backup_sets()

    if not backup_sets:
        raise RuntimeError(
            "Nenhum Backup Set foi encontrado no CloudBackupPRO."
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

    save_config(config)

    logger.info(
        "Configuração criada com %s Backup Set(s).",
        len(backup_sets),
    )

    return config


def configure_client() -> None:
    logger.info("Iniciando configuração manual do Backup_Auto.")

    create_configuration()
    register_startup()

    logger.info("Configuração do Backup_Auto concluída.")


def run_backup_auto() -> int:
    logger.info("Backup_Auto iniciado.")
    logger.info("Diretório base: %s", BASE_DIR)

    if not CONFIG_FILE.exists():
        logger.info(
            "Configuração não encontrada. Realizando configuração automática."
        )
        create_configuration()

    config = load_config()

    startup_delay = int(
        config.get("startup_delay", DEFAULT_STARTUP_DELAY)
    )

    configured_sets = config.get("backup_sets", [])

    if not configured_sets:
        raise RuntimeError(
            "Nenhum Backup Set foi configurado."
        )

    backup_sets = [
        BackupSet(
            name=item["name"],
            id=str(item["id"]),
        )
        for item in configured_sets
    ]

    logger.info(
        "Backup Sets configurados: %s",
        len(backup_sets),
    )

    if startup_delay > 0:
        logger.info(
            "Aguardando %s segundos para estabilização do Windows.",
            startup_delay,
        )
        time.sleep(startup_delay)

    cloudbackup = CloudBackup()

    success_count = 0
    failure_count = 0

    for index, backup_set in enumerate(backup_sets, start=1):
        logger.info(
            "Iniciando Backup Set %s/%s: %s [%s]",
            index,
            len(backup_sets),
            backup_set.name,
            backup_set.id,
        )

        try:
            result = cloudbackup.run_backup(backup_set)

            if result.success:
                success_count += 1

                logger.info(
                    "Backup concluído com êxito: %s [%s]",
                    backup_set.name,
                    backup_set.id,
                )
            else:
                failure_count += 1

                logger.error(
                    "Backup Set retornou falha: %s [%s]",
                    backup_set.name,
                    backup_set.id,
                )

        except Exception:
            failure_count += 1

            logger.exception(
                "Erro ao executar Backup Set: %s [%s]",
                backup_set.name,
                backup_set.id,
            )

    logger.info(
        "Total: %s | Sucesso: %s | Falhas: %s",
        len(backup_sets),
        success_count,
        failure_count,
    )

    return 0 if failure_count == 0 else 1


def main() -> int:
    configure_logging()

    try:
        if "--configure" in sys.argv:
            configure_client()
            return 0

        if "--remove-startup" in sys.argv:
            unregister_startup()
            return 0

        return run_backup_auto()

    except CloudBackupError as exc:
        logger.error(str(exc))
        return 1

    except Exception:
        logger.exception(
            "Erro inesperado no Backup_Auto."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())