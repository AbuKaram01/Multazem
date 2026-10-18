# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

import logging
import sys

_ROOT_LOGGER_NAME = "multazem"


class _ConsoleHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        stream = sys.stderr if record.levelno >= logging.WARNING else sys.stdout
        try:
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)


class _ComponentFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("[%(component)s] %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        record.component = record.name.rpartition(".")[2]
        return super().format(record)


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{component}")


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(level)
    root.propagate = False
    if any(isinstance(handler, _ConsoleHandler) for handler in root.handlers):
        return
    handler = _ConsoleHandler()
    handler.setFormatter(_ComponentFormatter())
    root.addHandler(handler)
