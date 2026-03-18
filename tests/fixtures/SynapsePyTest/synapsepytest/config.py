"""Application configuration — runs at import time."""
from synapsepytest.utils import format_name


def get_default_name() -> str:
    return "DefaultAnimal"


# Module-level call: config module calls get_default_name
DEFAULT_NAME: str = get_default_name()

# Module-level call: config module calls format_name from utils
FORMATTED_NAME: str = format_name(DEFAULT_NAME)
