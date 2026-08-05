import base64
import binascii
import html
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class CanonicalizedContent:
    text: str
    transformations: tuple[str, ...]
    truncated: bool


_INVISIBLE_CATEGORIES = {"Cf", "Cc"}
_CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "і": "i",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
    }
)
_SECURITY_VOCABULARY = (
    "ignore",
    "previous",
    "instructions",
    "system",
    "reveal",
    "developer",
    "message",
    "disregard",
)
_BASE64_TOKEN = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")
_HEX_TOKEN = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}){12,}(?![0-9a-fA-F])")
_HTML_TAG = re.compile(r"<[^>]{1,500}>")
_SPACED_CHARACTERS = re.compile(r"(?<!\w)(?:[A-Za-zÀ-ÿ][ \t]+){1,}[A-Za-zÀ-ÿ](?!\w)")


def canonicalize_content(
    content: str,
    *,
    max_chars: int = 1_000_000,
    max_decoded_chars: int = 4096,
) -> CanonicalizedContent:
    value = str(content or "")
    transformations: list[str] = []
    truncated = len(value) > max_chars
    if truncated:
        value = _distributed_sample(value, max_chars)
        transformations.append("CANONICAL_INPUT_SAMPLED")

    unescaped = html.unescape(value)
    if unescaped != value:
        transformations.append("CANONICAL_HTML_ENTITY")
        value = unescaped
    if _HTML_TAG.search(value):
        transformations.append("CANONICAL_HTML_MARKUP")
        value = _HTML_TAG.sub(" ", value)

    for _ in range(2):
        decoded_url = urllib.parse.unquote(value)
        if decoded_url == value:
            break
        transformations.append("CANONICAL_URL_ENCODING")
        value = decoded_url

    normalized = unicodedata.normalize("NFKC", value).translate(_CONFUSABLES)
    if normalized != value:
        transformations.append("CANONICAL_UNICODE_NFKC")
    value = normalized
    without_invisible = "".join(
        character
        for character in value
        if unicodedata.category(character) not in _INVISIBLE_CATEGORIES or character in "\n\t"
    )
    if without_invisible != value:
        transformations.append("CANONICAL_INVISIBLE_REMOVED")
        value = without_invisible

    # Duas ou mais lacunas delimitam palavras ofuscadas diferentes. O marcador
    # impede que a canonicalizacao funda essas palavras em um unico token.
    spacing_marker = " \u241f "
    spacing_safe = re.sub(r"[ \t]{2,}", spacing_marker, value)
    collapsed = _SPACED_CHARACTERS.sub(
        lambda match: re.sub(r"[ \t]+", "", match.group(0)),
        spacing_safe,
    ).replace("\u241f", " ")
    if collapsed != value:
        transformations.append("CANONICAL_CHARACTER_SPACING")
        value = collapsed

    decoded_fragments = []
    for token in dict.fromkeys(_BASE64_TOKEN.findall(value)):
        decoded = _decode_base64(token, max_decoded_chars)
        if decoded:
            decoded_fragments.append(decoded)
            transformations.append("CANONICAL_BASE64_DECODED")
    for token in dict.fromkeys(_HEX_TOKEN.findall(value)):
        decoded = _decode_hex(token, max_decoded_chars)
        if decoded:
            decoded_fragments.append(decoded)
            transformations.append("CANONICAL_HEX_DECODED")
    if decoded_fragments:
        value = f"{value}\n" + "\n".join(decoded_fragments)

    value = _fold_accents(value.casefold())
    repaired, typo_changed = _repair_security_typoglycemia(value)
    if typo_changed:
        transformations.append("CANONICAL_TYPOGLYCEMIA_REPAIRED")
        value = repaired
    return CanonicalizedContent(
        re.sub(r"\s+", " ", value).strip(),
        tuple(dict.fromkeys(transformations)),
        truncated,
    )


def _decode_base64(token: str, max_chars: int) -> str | None:
    try:
        decoded = base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError):
        return None
    return _safe_decoded_text(decoded, max_chars)


def _decode_hex(token: str, max_chars: int) -> str | None:
    try:
        decoded = bytes.fromhex(token)
    except ValueError:
        return None
    return _safe_decoded_text(decoded, max_chars)


def _safe_decoded_text(value: bytes, max_chars: int) -> str | None:
    if not value or len(value) > max_chars * 4:
        return None
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    printable = sum(character.isprintable() or character.isspace() for character in text)
    if not text or printable / len(text) < 0.9:
        return None
    return text[:max_chars]


def _repair_security_typoglycemia(value: str) -> tuple[str, bool]:
    changed = False

    def replace_token(match: re.Match) -> str:
        nonlocal changed
        token = match.group(0)
        if token in _SECURITY_VOCABULARY:
            return token
        candidate = max(
            _SECURITY_VOCABULARY,
            key=lambda word: SequenceMatcher(None, token, word).ratio(),
        )
        score = SequenceMatcher(None, token, candidate).ratio()
        if (
            token[0] == candidate[0]
            and token[-1] == candidate[-1]
            and abs(len(token) - len(candidate)) <= 1
            and score >= 0.78
        ):
            changed = True
            return candidate
        return token

    repaired = re.sub(r"\b[a-z]{4,14}\b", replace_token, value)
    return repaired, changed


def _fold_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _distributed_sample(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    window_count = 8
    window_size = max(1, max_chars // window_count)
    if len(value) <= window_size:
        return value
    last_start = max(0, len(value) - window_size)
    starts = {round(index * last_start / (window_count - 1)) for index in range(window_count)}
    return "\n".join(value[start : start + window_size] for start in sorted(starts))[:max_chars]
