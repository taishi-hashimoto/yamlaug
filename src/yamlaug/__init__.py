"yamlaug - YAML augmentation tool (non-destructive YAML upgrader)"

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

__version__ = "0.0.1"
