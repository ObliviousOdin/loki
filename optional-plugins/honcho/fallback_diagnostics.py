"""Retain fallback tracebacks without copying SDK response or credential text into logs."""
from __future__ import annotations

import sys


def redacted_exc_info():
    """Keep the call stack and exception class; provider exception messages can contain secrets."""
    error_type, error, traceback = sys.exc_info()
    if error is None:
        return None
    safe = RuntimeError(f"{error_type.__name__}: provider error details omitted")
    return RuntimeError, safe, traceback
