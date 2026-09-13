from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class CloudBackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupSet:
    name: str
    id: str


@dataclass(frozen=True)
class BackupResult:
    backup_set: BackupSet
    success: bool
    output: str


class CloudBackup:
    BACKUP_SET_PATTERN = re.compile(
        r"BackupSet\s+Name\s*=\s*(.*?)\s*,\s*ID\s*=\s*(\d+)",
        re.IGNORECASE,
    )

    SUCCESS_PATTERNS = (
        "backup concluído com êxito",
        "backup completed successfully",
    )

    ERROR_PATTERNS = (
        "[exception]",
        "backup falhou",
        "backup failed",
        " exception ",
        " error ",
        " erro ",
    )

    def __init__(
        self,
        app_home: str | Path | None = None,
        setting_home: str | Path | None = None,
    ) -> None:
        self.app_home = self._discover_app_home(app_home)
        self.bin_dir = self.app_home / "bin"
        self.setting_home = self._discover_setting_home(setting_home)

        self.bjw_exe = (
            self.app_home / "jvm" / "bin" / "bJW.exe"
        )

        self.list_backup_set = (
            self.bin_dir / "ListBackupSet.bat"
        )

        self.list_backup_job = (
            self.bin_dir / "ListBackupJob.bat"
        )

        self.run_backup_set = (
            self.bin_dir / "RunBackupSet.bat"
        )

        self._validate_installation()

    @staticmethod
    def _discover_app_home(
        app_home: str | Path | None,
    ) -> Path:
        if app_home:
            path = Path(app_home).expanduser()

            if path.is_dir():
                return path.resolve()

            raise CloudBackupError(
                f"CloudBackupPRO não encontrado em: {path}"
            )

        for variable in (
            "CLOUDBACKUPPRO_HOME",
            "CLOUD_BACKUP_PRO_HOME",
        ):
            value = os.environ.get(variable)

            if not value:
                continue

            path = Path(value).expanduser()

            if path.is_dir():
                return path.resolve()

        candidates = (
            Path(r"C:\Program Files\CloudBackupPRO"),
            Path(r"C:\Program Files (x86)\CloudBackupPRO"),
        )

        for path in candidates:
            if path.is_dir():
                return path.resolve()

        raise CloudBackupError(
            "Não foi possível localizar a instalação "
            "do CloudBackupPRO."
        )

    @staticmethod
    def _discover_setting_home(
        setting_home: str | Path | None,
    ) -> Path:
        if setting_home:
            path = Path(setting_home).expanduser()

            if path.is_dir():
                return path.resolve()

            raise CloudBackupError(
                f"SETTING_HOME não encontrado: {path}"
            )

        user_profile = os.environ.get("USERPROFILE")

        if not user_profile:
            raise CloudBackupError(
                "A variável USERPROFILE não está disponível."
            )

        path = Path(user_profile) / ".obm"

        if path.is_dir():
            return path.resolve()

        raise CloudBackupError(
            f"SETTING_HOME não encontrado: {path}"
        )

    def _validate_installation(self) -> None:
        if not self.app_home.is_dir():
            raise CloudBackupError(
                f"Diretório inválido: {self.app_home}"
            )

        if not self.bin_dir.is_dir():
            raise CloudBackupError(
                f"Diretório bin não encontrado: {self.bin_dir}"
            )

        required_files = (
            self.bjw_exe,
            self.list_backup_set,
            self.list_backup_job,
            self.run_backup_set,
            self.bin_dir / "cb.ini",
            self.bin_dir / "cb.jar",
        )

        missing = [
            str(path)
            for path in required_files
            if not path.is_file()
        ]

        if missing:
            raise CloudBackupError(
                "Arquivos necessários do CloudBackupPRO "
                "não encontrados:\n\n"
                + "\n".join(missing)
            )

    def _load_java_options(self) -> list[str]:
        ini_file = self.bin_dir / "cb.ini"

        try:
            lines = ini_file.read_text(
                encoding="utf-8",
                errors="ignore",
            ).splitlines()

        except OSError as exc:
            raise CloudBackupError(
                f"Não foi possível ler o arquivo cb.ini: {exc}"
            ) from exc

        options: list[str] = []

        for line in lines:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            options.extend(line.split())

        return options

    def _build_java_command(
        self,
        java_class: str,
        arguments: list[str],
    ) -> list[str]:
        library_path = (
            f"{self.bin_dir};"
            f"{self.bin_dir / 'X64'}"
        )

        classpath = (
            f"{self.bin_dir};"
            f"{self.bin_dir / 'cb.jar'}"
        )

        command = [
            str(self.bjw_exe),
            f"-Djava.library.path={library_path}",
            "-cp",
            classpath,
        ]

        command.extend(self._load_java_options())
        command.append(java_class)
        command.extend(arguments)

        return command

    def _run_java(
        self,
        java_class: str,
        arguments: list[str],
        timeout: int,
    ) -> str:
        command = self._build_java_command(
            java_class,
            arguments,
        )

        environment = os.environ.copy()

        java_bin = self.app_home / "jvm" / "bin"
        x64_bin = self.bin_dir / "X64"

        environment["PATH"] = (
            f"{java_bin};"
            f"{x64_bin};"
            f"{self.bin_dir};"
            f"{environment.get('PATH', '')}"
        )

        creation_flags = getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0,
        )

        try:
            result = subprocess.run(
                command,
                cwd=self.bin_dir,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=creation_flags,
                check=False,
            )

        except subprocess.TimeoutExpired as exc:
            raise CloudBackupError(
                f"Tempo limite excedido ao executar "
                f"o CloudBackupPRO: {java_class}"
            ) from exc

        except OSError as exc:
            raise CloudBackupError(
                "Não foi possível iniciar o CloudBackupPRO: "
                f"{exc}"
            ) from exc

        output = result.stdout or ""

        if result.returncode != 0:
            raise CloudBackupError(
                "O CloudBackupPRO retornou código "
                f"{result.returncode}.\n\n"
                f"Saída recebida:\n{output}"
            )

        return output

    def list_backup_sets(self) -> list[BackupSet]:
        output = self._run_java(
            "ListBackupSet",
            ["..", ""],
            timeout=120,
        )

        backup_sets = self._parse_backup_sets(output)

        if backup_sets:
            return backup_sets

        raise CloudBackupError(
            "O CloudBackupPRO foi executado, mas nenhum "
            "Backup Set foi identificado na saída.\n\n"
            f"Saída recebida:\n{output}"
        )

    def run_backup(
        self,
        backup_set: BackupSet,
        timeout: int = 7200,
    ) -> BackupResult:
        output = self._run_java(
            "RunBackupSet",
            [
                "..",
                backup_set.id,
                "ALL",
                "FILE",
                "",
                "",
                "DISABLE-CLEANUP",
                "DISABLE-DEBUG",
            ],
            timeout=timeout,
        )

        normalized_output = output.lower()

        success = any(
            pattern in normalized_output
            for pattern in self.SUCCESS_PATTERNS
        )

        has_error = any(
            pattern in normalized_output
            for pattern in self.ERROR_PATTERNS
        )

        return BackupResult(
            backup_set=backup_set,
            success=success and not has_error,
            output=output,
        )

    @classmethod
    def _parse_backup_sets(
        cls,
        output: str,
    ) -> list[BackupSet]:
        backup_sets: list[BackupSet] = []
        known_ids: set[str] = set()

        normalized_output = (
            output
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        for line in normalized_output.splitlines():
            line = line.strip()

            if not line:
                continue

            match = cls.BACKUP_SET_PATTERN.search(line)

            if not match:
                continue

            name = match.group(1).strip()
            backup_set_id = match.group(2).strip()

            if backup_set_id in known_ids:
                continue

            known_ids.add(backup_set_id)

            backup_sets.append(
                BackupSet(
                    name=name,
                    id=backup_set_id,
                )
            )

        return backup_sets

    def __repr__(self) -> str:
        return (
            "CloudBackup("
            f"app_home={self.app_home!r}, "
            f"setting_home={self.setting_home!r}"
            ")"
        )