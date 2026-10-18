# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

import logging

from multazem.logs import configure_logging, get_logger


def test_messages_carry_the_component_in_square_brackets(capsys):
    get_logger("scheduler").info("hello %s", "world")
    assert capsys.readouterr().out == "[scheduler] hello world\n"


def test_warnings_and_errors_go_to_stderr_and_the_rest_to_stdout(capsys):
    logger = get_logger("settings")
    logger.info("fine")
    logger.warning("careful")
    logger.error("broken")
    captured = capsys.readouterr()
    assert captured.out == "[settings] fine\n"
    assert captured.err == "[settings] careful\n[settings] broken\n"


def test_debug_messages_are_dropped_at_the_default_level(capsys):
    get_logger("window").debug("noise")
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_configuring_twice_does_not_duplicate_the_lines(capsys):
    configure_logging()
    configure_logging()
    get_logger("headless").info("once")
    assert capsys.readouterr().out == "[headless] once\n"


def test_the_application_loggers_do_not_propagate_to_the_root_logger():
    assert logging.getLogger("multazem").propagate is False
