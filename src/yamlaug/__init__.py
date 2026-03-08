"yamlaug - YAML augmentation tool (non-destructive YAML upgrader)"

from importlib.metadata import PackageNotFoundError, version

from .core import augment_text
from .file_api import augment_file
from .types import Report, WarningRecord


__all__ = [
    "__version__",
    "augment_text",
    "augment_file",
    "Report",
    "WarningRecord",
]

try:
    __version__ = version("yamlaug")
except PackageNotFoundError:
    __version__ = "0.0.0"
