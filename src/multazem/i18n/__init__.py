# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from .ar import MESSAGES as _ARABIC_MESSAGES
from .en import MESSAGES as _ENGLISH_MESSAGES

DEFAULT_LANGUAGE: Final = "en"

LANGUAGE_NAMES: Final[Mapping[str, str]] = {"en": "English", "ar": "العربية"}
SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = tuple(LANGUAGE_NAMES)

_RTL_LANGUAGES: Final = frozenset({"ar"})
_CATALOGS: Final[Mapping[str, Mapping[str, str]]] = {
    "en": _ENGLISH_MESSAGES,
    "ar": _ARABIC_MESSAGES,
}

_current_language = DEFAULT_LANGUAGE


def normalize_language(code: object) -> str:
    if isinstance(code, str) and code in SUPPORTED_LANGUAGES:
        return code
    return DEFAULT_LANGUAGE


def set_language(code: object) -> str:
    global _current_language
    _current_language = normalize_language(code)
    return _current_language


def current_language() -> str:
    return _current_language


def is_rtl(language: str | None = None) -> bool:
    return (language or _current_language) in _RTL_LANGUAGES


def tr(key: str, *, language: str | None = None, **params: Any) -> str:
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
    def __init__(self, key: str, **params: Any) -> None:
        self.key = key
        self.params = params
        super().__init__(tr(key, language=DEFAULT_LANGUAGE, **params))

    def localized(self, language: str | None = None) -> str:
        return tr(self.key, language=language, **self.params)


def describe_error(error: BaseException, language: str | None = None) -> str:
    if isinstance(error, LocalizedError):
        return error.localized(language)
    return str(error)
