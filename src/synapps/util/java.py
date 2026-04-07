from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess

log = logging.getLogger(__name__)

_MINIMUM_JAVA_VERSION = 17

# Matches the version string inside quotes from `java -version` output.
# Handles both modern ("17.0.1") and legacy ("1.8.0_362") formats.
_VERSION_PATTERN = re.compile(r'"(\d+)(?:\.(\d+))?')


def get_java_major_version() -> int | None:
    """Run ``java -version`` and return the major version number, or None if it cannot be determined."""
    java_path = shutil.which("java")
    if java_path is None:
        return None

    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        log.warning("java -version timed out")
        return None

    # java -version writes to stderr by JVM convention
    output = result.stderr or result.stdout or ""
    return parse_java_version(output)


def parse_java_version(version_output: str) -> int | None:
    """Extract the major version number from ``java -version`` output.

    Handles both modern format (``"17.0.1"``) where the first number is the
    major version, and legacy format (``"1.8.0_362"``) where ``1.X`` means
    Java X.
    """
    match = _VERSION_PATTERN.search(version_output)
    if not match:
        return None

    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) else 0

    # Legacy versioning: "1.8.0_362" means Java 8
    if major == 1 and minor > 0:
        return minor

    return major


def check_java_version(minimum: int = _MINIMUM_JAVA_VERSION) -> tuple[bool, int | None, str]:
    """Check that Java is installed and meets the minimum version requirement.

    Returns:
        A tuple of (ok, detected_version, message).
        ``ok`` is True when the version meets the minimum, False otherwise.
        ``detected_version`` is the parsed major version (or None).
        ``message`` is a human-readable explanation.
    """
    java_path = shutil.which("java")
    if java_path is None:
        return False, None, (
            "Java is not installed or is not on PATH.\n"
            + _install_instructions(minimum)
        )

    version = get_java_major_version()
    if version is None:
        return False, None, (
            "Could not determine the installed Java version.\n"
            + _install_instructions(minimum)
        )

    if version < minimum:
        return False, version, (
            f"Java {version} was detected but JDK {minimum}+ is required.\n"
            + _install_instructions(minimum)
        )

    return True, version, f"Java {version} detected (meets JDK {minimum}+ requirement)"


def _install_instructions(minimum: int) -> str:
    system = platform.system()
    lines = [f"Please install JDK {minimum}+ and ensure `java` points to the correct version."]
    if system == "Darwin":
        lines.append(f"  brew install --cask temurin")
    elif system == "Linux":
        lines.append(f"  sudo apt-get install openjdk-{minimum}-jdk")
    lines.append("  Or download from: https://adoptium.net/")
    lines.append("")
    lines.append("If you have multiple Java versions, set JAVA_HOME and update PATH:")
    lines.append("  export JAVA_HOME=/path/to/jdk-{0}".format(minimum))
    lines.append("  export PATH=\"$JAVA_HOME/bin:$PATH\"")
    return "\n".join(lines)
