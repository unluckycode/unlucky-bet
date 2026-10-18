"""Hasło do portalu (APP_PASSWORD): normalizacja, porównanie, diagnostyka."""

import hmac
import os
import unicodedata

QUOTES = ('"', "'", "\u201e", "\u201d", "\u201c")


def normalize_input(value):
    """Hasło wpisane w formularzu: bez białych znaków na brzegach, Unicode w postaci NFC."""
    return unicodedata.normalize("NFC", (value or "").strip())


def normalize_secret(raw):
    """Wartość ze zmiennej środowiskowej. Panele hostingów łatwo doklejają spację, znak nowej
    linii albo cudzysłowy wpisane razem z hasłem – usuwamy je, żeby nie psuły logowania."""
    value = (raw or "").strip()
    if len(value) >= 2 and value[0] in QUOTES and value[-1] in QUOTES:
        value = value[1:-1].strip()
    return unicodedata.normalize("NFC", value)


def describe_secret(raw):
    """Opis do logów bez ujawniania hasła."""
    value = normalize_secret(raw)
    if not value:
        return "APP_PASSWORD nie jest ustawione – logowanie wyłączone"
    notes = []
    if (raw or "") != (raw or "").strip():
        notes.append("usunięto białe znaki z początku/końca")
    stripped = (raw or "").strip()
    if len(stripped) >= 2 and stripped[0] in QUOTES and stripped[-1] in QUOTES:
        notes.append("usunięto otaczające cudzysłowy")
    if any(ord(c) > 127 for c in value):
        notes.append("zawiera znaki spoza ASCII (np. polskie litery)")
    return f"APP_PASSWORD ustawione: {len(value)} znaków" + (f" ({'; '.join(notes)})" if notes else "")


def configured_password():
    return normalize_secret(os.environ.get("APP_PASSWORD", ""))


def enabled():
    return bool(configured_password())


def check_password(candidate):
    expected = configured_password()
    if not expected:
        return False
    # compare_digest na bajtach – na str rzuca TypeError dla znaków spoza ASCII (np. „ą”, „ł”).
    return hmac.compare_digest(normalize_input(candidate).encode("utf-8"), expected.encode("utf-8"))
