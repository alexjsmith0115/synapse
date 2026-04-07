"""
Provides Eclipse JDT LS specific instantiation of the LanguageServer class.
Contains configurations and settings specific to Java language support.
"""

import glob
import hashlib
import logging
import os
import pathlib
import platform
import shutil
import threading
from typing import cast

from overrides import override
from sensai.util.logging import LogTime

from solidlsp.ls import LanguageServerDependencyProvider, LanguageServerDependencyProviderSinglePath, SolidLanguageServer
from solidlsp.ls_config import LanguageServerConfig
from solidlsp.lsp_protocol_handler.lsp_types import InitializeParams
from solidlsp.settings import SolidLSPSettings

from .common import RuntimeDependency, RuntimeDependencyCollection

log = logging.getLogger(__name__)

# Default JDT LS version
_DEFAULT_JDTLS_VERSION = "1.57.0"
_DEFAULT_JDTLS_TIMESTAMP = "202602261110"


class EclipseJDTLS(SolidLanguageServer):
    """
    Eclipse JDT Language Server implementation for Java support.

    You can pass the following entries in ls_specific_settings["java"]:
        - jdtls_version: Version of JDT LS to install (default: "1.40.0")
        - jdtls_timestamp: Build timestamp for the version (default: "202409261450")
    """

    def __init__(self, config: LanguageServerConfig, repository_root_path: str, solidlsp_settings: SolidLSPSettings):
        super().__init__(
            config,
            repository_root_path,
            None,
            "java",
            solidlsp_settings,
        )
        self.server_ready = threading.Event()

    def _create_dependency_provider(self) -> LanguageServerDependencyProvider:
        return self.DependencyProvider(self._custom_settings, self._ls_resources_dir)

    @override
    def _create_process_launch_info(self) -> "ProcessLaunchInfo":
        info = super()._create_process_launch_info()
        # JDT LS requires a writable Eclipse workspace (-data) to initialize.
        # Without it, the OSGi workspace plugin fails to start.
        path_hash = hashlib.sha256(self.repository_root_path.encode()).hexdigest()[:12]
        data_dir = os.path.join(self._ls_resources_dir, "workspaces", path_hash)
        os.makedirs(data_dir, exist_ok=True)
        info.cmd.extend(["-data", data_dir])
        return info

    @override
    def is_ignored_dirname(self, dirname: str) -> bool:
        return super().is_ignored_dirname(dirname) or dirname in [
            "target",
            "build",
            ".gradle",
            ".idea",
            "bin",
            ".settings",
            ".mvn",
        ]

    @staticmethod
    def _determine_log_level(line: str) -> int:
        return SolidLanguageServer._determine_log_level(line)

    class DependencyProvider(LanguageServerDependencyProviderSinglePath):
        def _get_or_install_core_dependency(self) -> str:
            """
            Ensure Java is available, download Eclipse JDT LS if needed,
            and return the path to the equinox launcher jar.
            """
            from synapps.util.java import check_java_version

            ok, version, message = check_java_version(minimum=17)
            if not ok:
                raise RuntimeError(message)

            language_specific_config = self._custom_settings
            jdtls_version = language_specific_config.get("jdtls_version", _DEFAULT_JDTLS_VERSION)
            jdtls_timestamp = language_specific_config.get("jdtls_timestamp", _DEFAULT_JDTLS_TIMESTAMP)

            jdtls_dir = os.path.join(self._ls_resources_dir, "jdtls")
            version_file = os.path.join(jdtls_dir, ".installed_version")
            expected_version = f"{jdtls_version}_{jdtls_timestamp}"

            needs_install = False
            if not os.path.exists(jdtls_dir):
                log.info("JDT LS directory not found at %s", jdtls_dir)
                needs_install = True
            elif os.path.exists(version_file):
                with open(version_file) as f:
                    installed_version = f.read().strip()
                if installed_version != expected_version:
                    log.info(
                        "JDT LS version mismatch: installed=%s, expected=%s. Reinstalling...",
                        installed_version, expected_version,
                    )
                    shutil.rmtree(jdtls_dir, ignore_errors=True)
                    needs_install = True
            else:
                log.info("JDT LS version file not found. Reinstalling to ensure correct version...")
                shutil.rmtree(jdtls_dir, ignore_errors=True)
                needs_install = True

            if needs_install:
                download_url = (
                    f"https://www.eclipse.org/downloads/download.php?"
                    f"file=/jdtls/milestones/{jdtls_version}/"
                    f"jdt-language-server-{jdtls_version}-{jdtls_timestamp}.tar.gz&r=1"
                )
                os.makedirs(jdtls_dir, exist_ok=True)

                tarball_path = os.path.join(jdtls_dir, "jdtls.tar.gz")
                deps = RuntimeDependencyCollection(
                    [
                        RuntimeDependency(
                            id="jdtls-download",
                            description="Eclipse JDT Language Server",
                            command=["curl", "-L", "-o", tarball_path, download_url],
                            platform_id="any",
                        ),
                        RuntimeDependency(
                            id="jdtls-extract",
                            description="Extract JDT LS tarball",
                            command=["tar", "-xzf", tarball_path, "-C", jdtls_dir],
                            platform_id="any",
                        ),
                    ]
                )

                log.info("Installing Eclipse JDT Language Server %s...", jdtls_version)
                with LogTime("Installation of Eclipse JDT LS", logger=log):
                    deps.install(jdtls_dir)

                # Clean up tarball
                if os.path.exists(tarball_path):
                    os.remove(tarball_path)

                # Write version marker
                with open(version_file, "w") as f:
                    f.write(expected_version)
                log.info("Eclipse JDT LS installed successfully")

            # Find the equinox launcher jar
            launcher_pattern = os.path.join(jdtls_dir, "plugins", "org.eclipse.equinox.launcher_*.jar")
            launcher_jars = glob.glob(launcher_pattern)
            if not launcher_jars:
                raise FileNotFoundError(
                    f"Equinox launcher jar not found at {launcher_pattern}. "
                    "JDT LS installation may be corrupted."
                )
            return launcher_jars[0]

        def _create_launch_command(self, core_path: str) -> list[str]:
            jdtls_dir = os.path.join(self._ls_resources_dir, "jdtls")

            system = platform.system().lower()
            if system == "darwin":
                config_name = "config_mac"
            elif system == "linux":
                config_name = "config_linux"
            else:
                config_name = "config_win"

            config_dir = os.path.join(jdtls_dir, config_name)

            return [
                "java",
                "-Declipse.application=org.eclipse.jdt.ls.core.id1",
                "-Dosgi.bundles.defaultStartLevel=4",
                "-Declipse.product=org.eclipse.jdt.ls.core.product",
                "-Dlog.protocol=true",
                "-Dlog.level=ALL",
                "-jar", core_path,
                "-configuration", config_dir,
                "--add-modules=ALL-SYSTEM",
                "--add-opens", "java.base/java.util=ALL-UNNAMED",
                "--add-opens", "java.base/java.lang=ALL-UNNAMED",
            ]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        root_uri = pathlib.Path(repository_absolute_path).as_uri()
        initialize_params = {
            "locale": "en",
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True, "dynamicRegistration": True},
                    "completion": {"dynamicRegistration": True, "completionItem": {"snippetSupport": True}},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "hierarchicalDocumentSymbolSupport": True,
                        "symbolKind": {"valueSet": list(range(1, 27))},
                    },
                    "hover": {"dynamicRegistration": True, "contentFormat": ["markdown", "plaintext"]},
                    "signatureHelp": {"dynamicRegistration": True},
                    "codeAction": {"dynamicRegistration": True},
                    "rename": {"dynamicRegistration": True, "prepareSupport": True},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "didChangeConfiguration": {"dynamicRegistration": True},
                    "symbol": {"dynamicRegistration": True},
                },
            },
            "initializationOptions": {
                "settings": {
                    "java": {
                        "home": None,
                    },
                },
            },
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": root_uri,
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": os.path.basename(repository_absolute_path),
                }
            ],
        }
        return cast(InitializeParams, initialize_params)

    def _start_server(self) -> None:
        """
        Starts the Eclipse JDT Language Server and waits for it to be ready.
        """

        def register_capability_handler(params: dict) -> None:
            assert "registrations" in params
            return

        def do_nothing(params: dict) -> None:
            return

        def window_log_message(msg: dict) -> None:
            log.info("LSP: window/logMessage: %s", msg)

        def progress_handler(params: dict) -> None:
            value = params.get("value", {})
            if isinstance(value, dict) and value.get("kind") == "end":
                self.server_ready.set()

        def language_status_handler(params: dict) -> None:
            # JDT LS 1.57+ signals readiness via language/status notification
            if params.get("type") == "ServiceReady":
                self.server_ready.set()

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", progress_handler)
        self.server.on_notification("language/status", language_status_handler)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        log.info("Starting Eclipse JDT LS server process")
        self.server.start()
        initialize_params = self._get_initialize_params(self.repository_root_path)

        log.info("Sending initialize request from LSP client to JDT LS server")
        self.server.send.initialize(initialize_params)

        self.server.notify.initialized({})

        # JDT LS is slower to initialize than other servers
        if self.server_ready.wait(timeout=30.0):
            log.info("Eclipse JDT LS server is ready")
        else:
            log.info("Timeout waiting for JDT LS to become ready, proceeding anyway")
            self.server_ready.set()

    @override
    def _get_wait_time_for_cross_file_referencing(self) -> float:
        return 5
