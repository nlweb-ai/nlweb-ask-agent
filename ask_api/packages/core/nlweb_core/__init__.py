"""NLWeb Core library."""

__version__ = "0.5.0"

import os

from nlweb_core.summarizer import (
    ResultsSummarizer,
    SummaryResult,
    create_default_summarizer,
)
from nlweb_core.handler import NLWebHandler
from nlweb_core.azure_credentials import (
    get_azure_credential,
    get_openai_token_provider,
    close_credential,
)

__all__ = [
    "NLWebHandler",
    "ResultsSummarizer",
    "SummaryResult",
    "create_default_summarizer",
    "get_azure_credential",
    "get_openai_token_provider",
    "close_credential",
]
