"""Deterministic, context-managed appointment logging.

The logger writes ``[log] opened`` and ``[log] closed`` exactly once per
``with logger.session() as log:`` block.  Action messages are supplied by the
Clinic; failed actions use the exact brief format, for example::

    FAILED cancel #3: too late

Logging is best-effort: a broken sink or file never replaces the primary
domain exception, and never leaves the session open.
"""

from __future__ import annotations

import sys


class _LogSession:
    """One context-managed logging transaction."""

    def __init__(self, logger: "AppointmentLogger") -> None:
        self._logger = logger
        self._closed = False

    def __enter__(self) -> "_LogSession":
        if self._logger._active:
            raise RuntimeError("nested appointment-log sessions are not allowed")
        self._logger._active = True
        try:
            self._logger._emit("[log] opened")
        except Exception:
            self._logger._active = False
            raise
        return self

    def write(self, message: object) -> None:
        """Record an action or failure line."""

        self._logger._emit(str(message))

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if self._closed:
            return False
        self._closed = True
        try:
            self._logger._emit("[log] closed")
        finally:
            self._logger._active = False
        # Never suppress the domain exception that caused the exit.
        return False


class AppointmentLogger:
    """Collect and display appointment-log records.

    Parameters
    ----------
    sink:
        Callable accepting one string.  Defaults to ``print``.  Tests can pass
        ``lines.append`` or a deliberately failing callable.
    path:
        Optional file path.  Each record is appended as one line.  A file
        failure is reported to stderr and does not abort the domain operation.
    """

    def __init__(self, sink=None, path=None) -> None:
        self._sink = print if sink is None else sink
        self._path = path
        self._entries: list[str] = []
        self._active = False

    @property
    def entries(self) -> tuple[str, ...]:
        """Defensive copy of all records emitted so far."""

        return tuple(self._entries)

    def session(self) -> _LogSession:
        """Open one exactly-once logging transaction."""

        return _LogSession(self)

    def _emit(self, message: str) -> None:
        # Record first so the audit trail survives a display failure.
        self._entries.append(message)
        self._write_sink(message)
        self._write_file(message)

    def _write_sink(self, message: str) -> None:
        try:
            self._sink(message)
        except Exception as exc:  # display failures must not mask domain errors
            self._fallback(f"appointment log sink failed: {exc}")

    def _write_file(self, message: str) -> None:
        if self._path is None:
            return
        try:
            with open(self._path, "a", encoding="utf-8") as handle:
                handle.write(message + "\n")
        except OSError as exc:
            self._fallback(f"appointment log file failed: {exc}")

    @staticmethod
    def _fallback(message: str) -> None:
        try:
            print(f"[log] error: {message}", file=sys.stderr)
        except Exception:
            # Last-resort guard: a logging failure is never allowed to escape.
            pass
