from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


class CloudBackupError(RuntimeError):
    """Erro relacionado à integração com o CloudBackupPRO."""


@dataclass(frozen=True)
class BackupSet:
    name: str
    id: str


class CloudBackup:
    """
    Integração com o CloudBackupPRO.

    Nesta etapa:

    - localiza automaticamente a instalação;
    - localiza o SETTING_HOME;
    - valida a instalação;
    - executa o mecanismo oficial de descoberta;
    - descobre Backup Sets sem IDs hardcoded.
    """

    BACKUP_SET_PATTERN = re.compile(
        r"BackupSet\s+Name\s*=\s*(.*?)\s*,\s*ID\s*=\s*(\d+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        app_home: str | Path | None = None,
        setting_home: str | Path | None = None,
    ) -> None:

        self.app_home = self._discover_app_home(
            app_home
        )

        self.bin_dir = self.app_home / "bin"

        self.setting_home = self._discover_setting_home(
            setting_home
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

        self.java_exe = (
            self.app_home
            / "jvm"
            / "bin"
            / "bJW.exe"
        )

        self.cb_jar = (
            self.bin_dir / "cb.jar"
        )

        self.cb_ini = (
            self.bin_dir / "cb.ini"
        )

        self._validate_installation()

    # ================================================================
    # DESCOBRIR INSTALAÇÃO
    # ================================================================

    @staticmethod
    def _discover_app_home(
        app_home: str | Path | None,
    ) -> Path:

        if app_home:

            path = Path(
                app_home
            ).expanduser()

            if path.exists():
                return path.resolve()

            raise CloudBackupError(
                f"CloudBackupPRO não encontrado em: {path}"
            )

        for variable in (
            "CLOUDBACKUPPRO_HOME",
            "CLOUD_BACKUP_PRO_HOME",
        ):

            value = os.environ.get(
                variable
            )

            if not value:
                continue

            path = Path(
                value
            ).expanduser()

            if path.exists():
                return path.resolve()

        candidates = [
            Path(
                r"C:\Program Files\CloudBackupPRO"
            ),
            Path(
                r"C:\Program Files (x86)\CloudBackupPRO"
            ),
        ]

        for path in candidates:

            if path.exists():
                return path.resolve()

        raise CloudBackupError(
            "Não foi possível localizar a instalação "
            "do CloudBackupPRO."
        )

    # ================================================================
    # DESCOBRIR SETTING_HOME
    # ================================================================

    @staticmethod
    def _discover_setting_home(
        setting_home: str | Path | None,
    ) -> Path:

        if setting_home:

            path = Path(
                setting_home
            ).expanduser()

            if path.exists():
                return path.resolve()

            raise CloudBackupError(
                f"SETTING_HOME não encontrado em: {path}"
            )

        user_profile = os.environ.get(
            "USERPROFILE"
        )

        if not user_profile:

            raise CloudBackupError(
                "A variável USERPROFILE não está disponível."
            )

        path = (
            Path(user_profile)
            / ".obm"
        )

        if path.exists():
            return path.resolve()

        raise CloudBackupError(
            f"SETTING_HOME não encontrado: {path}"
        )

    # ================================================================
    # VALIDAR INSTALAÇÃO
    # ================================================================

    def _validate_installation(self) -> None:

        if not self.app_home.is_dir():

            raise CloudBackupError(
                f"Diretório inválido: {self.app_home}"
            )

        if not self.bin_dir.is_dir():

            raise CloudBackupError(
                f"Diretório bin não encontrado: "
                f"{self.bin_dir}"
            )

        required_files = [
            self.list_backup_set,
            self.list_backup_job,
            self.run_backup_set,
            self.java_exe,
            self.cb_jar,
            self.cb_ini,
        ]

        missing = [
            str(path)
            for path in required_files
            if not path.exists()
        ]

        if missing:

            raise CloudBackupError(
                "Arquivos necessários do CloudBackupPRO "
                "não encontrados:\n\n"
                + "\n".join(missing)
            )

    # ================================================================
    # LER CB.INI
    # ================================================================

    def _read_java_options(self) -> list[str]:
        """
        Lê o cb.ini utilizado pelo launcher oficial.

        Cada linha do arquivo representa uma opção da JVM.
        """

        try:

            content = self.cb_ini.read_text(
                encoding="utf-8",
                errors="replace",
            )

        except OSError as exc:

            raise CloudBackupError(
                f"Não foi possível ler {self.cb_ini}: {exc}"
            ) from exc

        options: list[str] = []

        for line in content.splitlines():

            line = line.strip()

            if not line:
                continue

            options.append(
                line
            )

        return options

    # ================================================================
    # LISTAR BACKUP SETS
    # ================================================================

    def list_backup_sets(self) -> list[BackupSet]:
        """
        Descobre os Backup Sets utilizando o mecanismo oficial
        do CloudBackupPRO.

        O launcher oficial utiliza:

            bJW.exe
            cb.jar
            cb.ini

        e executa:

            ListBackupSet .. <SETTING_HOME>

        Nesta implementação não utilizamos o BAT para fazer
        a captura da saída.
        """

        java_options = (
            self._read_java_options()
        )

        # ------------------------------------------------------------
        # Ambiente do CloudBackupPRO
        # ------------------------------------------------------------

        environment = os.environ.copy()

        x64_directory = (
            self.bin_dir
            / "X64"
        )

        jvm_bin_directory = (
            self.app_home
            / "jvm"
            / "bin"
        )

        current_path = environment.get(
            "PATH",
            "",
        )

        environment["PATH"] = (
            f"{x64_directory};"
            f"{jvm_bin_directory};"
            f"{current_path}"
        )

        # ------------------------------------------------------------
        # JAVA_LIB_PATH utilizado pelo BAT oficial.
        # ------------------------------------------------------------

        java_library_path = (
            f"-Djava.library.path="
            f"{self.bin_dir};"
            f"{x64_directory}"
        )

        # ------------------------------------------------------------
        # Classpath utilizado pelo BAT oficial.
        #
        # Utilizamos caminhos absolutos para evitar problemas
        # de diretório de trabalho.
        # ------------------------------------------------------------

        classpath = (
            f"{self.bin_dir};"
            f"{self.cb_jar}"
        )

        # ------------------------------------------------------------
        # Comando equivalente ao:
        #
        # bJW.exe
        #   -Djava.library.path=...
        #   -cp ...
        #   [JAVA_OPTS]
        #   ListBackupSet ..
        #
        # O segundo argumento é o SETTING_HOME.
        # ------------------------------------------------------------

        command = [
            str(self.java_exe),
            java_library_path,
            "-cp",
            classpath,
            *java_options,
            "ListBackupSet",
            str(self.app_home),
            str(self.setting_home),
        ]

        try:

            process = subprocess.run(
                command,
                cwd=str(
                    self.bin_dir
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="cp850",
                errors="replace",
                timeout=30,
                shell=False,
                env=environment,
            )

        except subprocess.TimeoutExpired as exc:

            raise CloudBackupError(
                "O mecanismo Java do CloudBackupPRO "
                "não terminou dentro de 30 segundos."
            ) from exc

        except OSError as exc:

            raise CloudBackupError(
                "Não foi possível executar o launcher "
                f"do CloudBackupPRO: {exc}"
            ) from exc

        stdout = process.stdout or ""
        stderr = process.stderr or ""

        # ------------------------------------------------------------
        # Diagnóstico.
        # ------------------------------------------------------------

        print()
        print(
            "Saída do mecanismo oficial:"
        )
        print(
            "----------------------------------"
        )

        if stdout.strip():

            print(
                stdout.strip()
            )

        else:

            print(
                "(nenhuma saída em STDOUT)"
            )

        if stderr.strip():

            print()
            print(
                "STDERR:"
            )
            print(
                stderr.strip()
            )

        print(
            "----------------------------------"
        )

        # ------------------------------------------------------------
        # Procurar Backup Sets.
        # ------------------------------------------------------------

        combined_output = (
            stdout
            + "\n"
            + stderr
        )

        backup_sets = (
            self._parse_backup_sets(
                combined_output
            )
        )

        if backup_sets:

            return backup_sets

        # ------------------------------------------------------------
        # Diagnóstico detalhado.
        # ------------------------------------------------------------

        details: list[str] = []

        details.append(
            "O mecanismo oficial foi executado, "
            "mas nenhum Backup Set foi identificado."
        )

        if stdout.strip():

            details.append(
                "STDOUT:\n"
                + stdout.strip()
            )

        if stderr.strip():

            details.append(
                "STDERR:\n"
                + stderr.strip()
            )

        details.append(
            f"Código de retorno: "
            f"{process.returncode}"
        )

        raise CloudBackupError(
            "\n\n".join(details)
        )

    # ================================================================
    # PARSER
    # ================================================================

    @classmethod
    def _parse_backup_sets(
        cls,
        output: str,
    ) -> list[BackupSet]:

        backup_sets: list[BackupSet] = []

        normalized_output = (
            output
            .replace(
                "\r\n",
                "\n",
            )
            .replace(
                "\r",
                "\n",
            )
        )

        for line in normalized_output.splitlines():

            line = line.strip()

            if not line:
                continue

            match = (
                cls.BACKUP_SET_PATTERN.search(
                    line
                )
            )

            if not match:
                continue

            name = (
                match.group(1)
                .strip()
            )

            backup_set_id = (
                match.group(2)
                .strip()
            )

            backup_sets.append(
                BackupSet(
                    name=name,
                    id=backup_set_id,
                )
            )

        return backup_sets

    # ================================================================
    # REPRESENTAÇÃO
    # ================================================================

    def __repr__(self) -> str:

        return (
            "CloudBackup("
            f"app_home={self.app_home!r}, "
            f"setting_home={self.setting_home!r}"
            ")"
        )