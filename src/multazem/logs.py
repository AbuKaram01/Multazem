# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Console logging for the application's ``multazem.*`` loggers.

Every record is printed as ``[component] message``, where the component is the last part of
the logger name (``multazem.scheduler`` prints as ``[scheduler]``). Records below WARNING go to
standard output, the others to standard error, which is what ``journalctl`` shows for the
background service.
"""

import logging
import sys

_ROOT_LOGGER_NAME = "multazem"


class _ConsoleHandler(logging.Handler):
    """Writes records to stdout, or to stderr from WARNING upwards.

    The stream is looked up for every record instead of being captured when the handler is
    created, so a redirected ``sys.stdout``/``sys.stderr`` (as in tests) receives the output.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Formats and writes one record; a failure is reported through ``handleError`` and never raised."""
        stream = sys.stderr if record.levelno >= logging.WARNING else sys.stdout
        try:
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:  # noqa: BLE001 - emit() must never raise; the logging module reports it
            self.handleError(record)


class _ComponentFormatter(logging.Formatter):
    """Formats a record as ``[component] message``."""

    def __init__(self) -> None:
        super().__init__("[%(component)s] %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        """Adds the ``component`` field to the record, then formats it."""
        record.component = record.name.rpartition(".")[2]
        return super().format(record)


def get_logger(component: str) -> logging.Logger:
    """Returns the logger of one component of the application.

    Args:
        component: Short component name, such as ``"scheduler"``; it appears in brackets in the output.
    """
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{component}")


def configure_logging(level: int = logging.INFO) -> None:
    """Sends the application's log records to the console.

    Safe to call more than once: the handler is attached a single time. The ``multazem`` logger does
    not propagate to the root logger, so the output looks the same whether or not the host program
    configured logging itself.

    Args:
        level: Lowest level that is shown.
    """
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(level)
    root.propagate = False
    if any(isinstance(handler, _ConsoleHandler) for handler in root.handlers):
        return
    handler = _ConsoleHandler()
    handler.setFormatter(_ComponentFormatter())
    root.addHandler(handler)
