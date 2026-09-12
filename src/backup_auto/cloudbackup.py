from __future__ import annotations

import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from winpty import PtyProcess


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

    def _run_command(
        self,
        command: str,
        timeout: int,
    ) -> str:
        process = None
        output: list[str] = []
        started_at = time.monotonic()

        try:
            try:
                process = PtyProcess.spawn(
                    command,
                    backend=0,
                )
            except BaseException as exc:
                raise CloudBackupError(
                    "Não foi possível iniciar o processo "
                    "do CloudBackupPRO através do ConPTY: "
                    f"{exc}"
                ) from exc

            while process.isalive():
                if time.monotonic() - started_at > timeout:
                    try:
                        process.terminate()
                    except Exception:
                        pass

                    raise CloudBackupError(
                        f"Tempo limite excedido ao executar: {command}"
                    )

                try:
                    data = process.read(4096)

                    if data:
                        output.append(data)

                except EOFError:
                    break

                time.sleep(0.05)

            try:
                while True:
                    data = process.read(4096)

                    if not data:
                        break

                    output.append(data)

            except EOFError:
                pass

        except CloudBackupError:
            raise

        except Exception as exc:
            raise CloudBackupError(
                "Não foi possível executar o CloudBackupPRO: "
                f"{exc}"
            ) from exc

        return "".join(output)

    def _create_list_backup_set_bridge(self) -> Path:
        bridge_file = Path(tempfile.gettempdir()) / (
            f"backup_auto_list_sets_{os.getpid()}.bat"
        )

        content = (
            "@echo off\r\n"
            "setlocal EnableDelayedExpansion\r\n"
            f'cd /d "{self.bin_dir}"\r\n'
            "\r\n"
            "set APP_HOME=..\r\n"
            "set JAVA_HOME=%APP_HOME%\\jvm\r\n"
            "set JAVA_EXE=%JAVA_HOME%\\bin\\bJW.exe\r\n"
            "set JAVA_LIB_PATH=-Djava.library.path=%APP_HOME%\\bin;%APP_HOME%\\bin\\X64\r\n"
            "set PATH=%JAVA_HOME%\\bin;%PATH%\r\n"
            "set CLASSPATH=%APP_HOME%\\bin;%APP_HOME%\\bin\\cb.jar\r\n"
            "\r\n"
            'set "DEP_LIB_PATH=X64"\r\n'
            "set INI_FILE=cb.ini\r\n"
            "set JAVA_OPTS=\r\n"
            "\r\n"
            'for /f "tokens=* delims=" %%A in (\'findstr /V /R "^[#]" "%INI_FILE%"\') do (\r\n'
            '    set "line=%%A"\r\n'
            '    if not "!line!"=="" set JAVA_OPTS=!JAVA_OPTS! !line!\r\n'
            ")\r\n"
            "\r\n"
            "set PATH=%CD%\\%APP_HOME%\\bin\\%DEP_LIB_PATH%;%PATH%\r\n"
            "set JAVA_LIB_PATH=%JAVA_LIB_PATH%\r\n"
            "\r\n"
            "%JAVA_EXE% %JAVA_LIB_PATH% -cp %CLASSPATH% %JAVA_OPTS% "
            'ListBackupSet %APP_HOME% ""\r\n'
            "exit /b %ERRORLEVEL%\r\n"
        )

        try:
            bridge_file.write_text(
                content,
                encoding="ascii",
                errors="ignore",
            )

        except OSError as exc:
            raise CloudBackupError(
                "Não foi possível criar o launcher temporário "
                f"para listar os Backup Sets: {exc}"
            ) from exc

        return bridge_file

    def _create_backup_bridge(
        self,
        backup_set: BackupSet,
    ) -> Path:
        bridge_file = Path(tempfile.gettempdir()) / (
            f"backup_auto_run_{os.getpid()}_{backup_set.id}.bat"
        )

        content = (
            "@echo off\r\n"
            "setlocal EnableDelayedExpansion\r\n"
            f'cd /d "{self.bin_dir}"\r\n'
            "\r\n"
            "set APP_HOME=..\r\n"
            "set JAVA_HOME=%APP_HOME%\\jvm\r\n"
            "set JAVA_EXE=%JAVA_HOME%\\bin\\bJW.exe\r\n"
            "set JAVA_LIB_PATH=-Djava.library.path=%APP_HOME%\\bin\r\n"
            "set PATH=%JAVA_HOME%\\bin;%PATH%\r\n"
            "set CLASSPATH=%APP_HOME%\\bin;%APP_HOME%\\bin\\cb.jar\r\n"
            "\r\n"
            'set "DEP_LIB_PATH=X64"\r\n'
            "set INI_FILE=cb.ini\r\n"
            "set JAVA_OPTS=\r\n"
            "\r\n"
            'for /f "tokens=* delims=" %%A in (\'findstr /V /R "^[#]" "%INI_FILE%"\') do (\r\n'
            '    set "line=%%A"\r\n'
            '    if not "!line!"=="" set JAVA_OPTS=!JAVA_OPTS! !line!\r\n'
            ")\r\n"
            "\r\n"
            "set PATH=%CD%\\%APP_HOME%\\bin\\%DEP_LIB_PATH%;%PATH%\r\n"
            "set JAVA_LIB_PATH=%JAVA_LIB_PATH%;%APP_HOME%\\bin\\%DEP_LIB_PATH%\r\n"
            "\r\n"
            f'echo Running Backup Set - "{backup_set.id}" ...\r\n'
            "%JAVA_EXE% %JAVA_LIB_PATH% -cp %CLASSPATH% %JAVA_OPTS% "
            f'RunBackupSet %APP_HOME% "{backup_set.id}" "ALL" "FILE" "" "" '
            '"DISABLE-CLEANUP" "DISABLE-DEBUG"\r\n'
            "exit /b %ERRORLEVEL%\r\n"
        )

        try:
            bridge_file.write_text(
                content,
                encoding="ascii",
                errors="ignore",
            )

        except OSError as exc:
            raise CloudBackupError(
                "Não foi possível criar o launcher temporário "
                f"do Backup Set: {exc}"
            ) from exc

        return bridge_file

    def _run_bridge(
        self,
        bridge_file: Path,
        timeout: int,
    ) -> str:
        command = (
            "C:\\Windows\\System32\\cmd.exe "
            f"/d /c {bridge_file} < NUL"
        )

        return self._run_command(
            command,
            timeout,
        )

    def list_backup_sets(self) -> list[BackupSet]:
        bridge_file = self._create_list_backup_set_bridge()

        try:
            output = self._run_bridge(
                bridge_file,
                timeout=120,
            )

        finally:
            try:
                bridge_file.unlink(missing_ok=True)
            except OSError:
                pass

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
        bridge_file = self._create_backup_bridge(
            backup_set
        )

        try:
            output = self._run_bridge(
                bridge_file,
                timeout,
            )

        finally:
            try:
                bridge_file.unlink(missing_ok=True)
            except OSError:
                pass

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