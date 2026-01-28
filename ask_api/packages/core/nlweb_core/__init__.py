"""NLWeb Core library."""

__version__ = "0.5.0"

import os

from nlweb_core.summarizer import (
    ResultsSummarizer,
    SummaryResult,
    create_default_summarizer,
)
from nlweb_core.handler import NLWebHandler

__all__ = [
    "NLWebHandler",
    "ResultsSummarizer",
    "SummaryResult",
    "create_default_summarizer",
]
