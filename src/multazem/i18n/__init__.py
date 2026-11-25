# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Runtime localisation for the UI, notifications and user-facing errors.

Design notes:
    * Catalogs are plain Python dictionaries (``en.py`` / ``ar.py``) rather than gettext
      ``.mo`` files. Packaging stays trivial (no compile step, no locale install paths) and
      the language can be switched at runtime without restarting the process, which is what
      the in-app language selector needs.
    * Messages are addressed by semantic dotted keys (``"window.next_prayer"``) and filled in
      with :meth:`str.format`. A completeness test guarantees that both catalogs define the
      same keys with the same placeholders.
    * English is the default language and the fallback for any key a catalog lacks.

This package is a leaf of the dependency graph: it must not import anything else from
``multazem`` so that every other layer can depend on it freely.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .ar import MESSAGES as _ARABIC_MESSAGES
from .en import MESSAGES as _ENGLISH_MESSAGES

DEFAULT_LANGUAGE: Final = "en"

LANGUAGE_NAMES: Final[Mapping[str, str]] = {"en": "English", "ar": "العربية"}
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = tuple(LANGUAGE_NAMES)

# Languages written right to left; the UI mirrors its layout for them.
_RTL_LANGUAGES: Final = frozenset({"ar"})
_CATALOGS: Final[Mapping[str, Mapping[str, str]]] = {
    "en": _ENGLISH_MESSAGES,
    "ar": _ARABIC_MESSAGES,
}

_current_language = DEFAULT_LANGUAGE


def normalize_language(code: object) -> str:
    """Returns ``code`` if it is a supported language, otherwise the default language."""
    if isinstance(code, str) and code in SUPPORTED_LANGUAGES:
        return code
    return DEFAULT_LANGUAGE


def set_language(code: object) -> str:
    """Selects the process-wide UI language and returns the code that was applied.

    An unsupported ``code`` selects the default language.
    """
    global _current_language  # noqa: PLW0603 - the language is one process-wide setting
    _current_language = normalize_language(code)
    return _current_language


def current_language() -> str:
    """Returns the code of the process-wide UI language."""
    return _current_language


def is_rtl(language: str | None = None) -> bool:
    """Returns whether ``language`` (default: the current one) is written right to left."""
    return (language or _current_language) in _RTL_LANGUAGES


def tr(key: str, *, language: str | None = None, **params: Any) -> str:
    """Translates ``key`` and substitutes ``params`` into the message.

    ``language`` overrides the process-wide language; this lets background code (such as
    the notification scheduler) render text for the configured language without touching
    global state. A missing key falls back to English and finally to the key itself, so a
    forgotten translation degrades gracefully instead of breaking the UI. A template that does not
    fit ``params`` is returned unformatted instead of raising.

    Args:
        key: Dotted message key such as ``"window.next_prayer"``.
        language: Language code to use instead of the current one.
        **params: Values for the ``{placeholders}`` of the message.
    """
    lang = _current_language if language is None else normalize_language(language)
    template = _CATALOGS[lang].get(key)
    if template is None:
        template = _CATALOGS[DEFAULT_LANGUAGE].get(key, key)
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        return template


class LocalizedError(ValueError):
    """A ``ValueError`` whose message can be rendered in any supported language.

    ``str(error)`` is always English, which keeps logs and test assertions stable;
    user-facing code calls :meth:`localized` to get text in the active language.

    Args:
        key: Message key in the catalogs.
        **params: Values for the message's placeholders.

    Attributes:
        key: The message key.
        params: The placeholder values.
    """

    def __init__(self, key: str, **params: Any) -> None:
        self.key = key
        self.params = params
        super().__init__(tr(key, language=DEFAULT_LANGUAGE, **params))

    def localized(self, language: str | None = None) -> str:
        """Returns the message in ``language`` (default: the current UI language)."""
        return tr(self.key, language=language, **self.params)


def describe_error(error: BaseException, language: str | None = None) -> str:
    """Returns the best user-facing text for ``error`` (localized when the error supports it)."""
    if isinstance(error, LocalizedError):
        return error.localized(language)
    return str(error)
