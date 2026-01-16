from __future__ import annotations

import re
from typing import Dict, List, Sequence

_NLLB_CODE_RE = re.compile(
    r"^[a-z]{3}_(Latn|Cyrl|Arab|Hans|Hant|Deva|Beng|Taml|Telu|Thai|Ethi|Grek|Hebr|Jpan|Hang|Kore|Mlym|Tibt|Geor|Knda|Mymr|Sinh)$"
)

# Small alias table: ISO-639-1 / common tags -> ISO-639-3
# (You can extend over time; this is enough for the usual UI languages)
ISO_ALIAS_TO_ISO3: Dict[str, str] = {
    "en": "eng",
    "ru": "rus",
    "de": "deu",
    "uk": "ukr",
    "fr": "fra",
    "es": "spa",
    "it": "ita",
    "pt": "por",
    "pl": "pol",
    "tr": "tur",
    "bg": "bul",
    "sr": "srp",
    "hr": "hrv",
    "sl": "slv",
    "el": "ell",
    "he": "heb",
    "ar": "arb",  # NLLB uses arb_Arab
    "fa": "pes",  # Persian often pes_Arab
    "ur": "urd",
    "hi": "hin",
    "bn": "ben",
    "ta": "tam",
    "te": "tel",
    "id": "ind",
    "ms": "zsm",
    "vi": "vie",
    "th": "tha",
    "ja": "jpn",
    "ko": "kor",
    "zh": "zho",
    "zh-cn": "zho",
    "zh-tw": "zho",
}


def extract_nllb_lang_codes(tokenizer) -> List[str]:
    add: Sequence[str] = []
    try:
        sp = getattr(tokenizer, "special_tokens_map_extended", None) or {}
        add = sp.get("additional_special_tokens") or []
    except Exception:
        add = []

    if not add:
        try:
            add = getattr(tokenizer, "additional_special_tokens", None) or []
        except Exception:
            add = []

    codes = []
    for t in add:
        if isinstance(t, str) and _NLLB_CODE_RE.match(t):
            codes.append(t)

    return sorted(set(codes))


def build_iso3_index(nllb_codes: Sequence[str]) -> Dict[str, List[str]]:
    idx: Dict[str, List[str]] = {}
    for c in nllb_codes:
        iso3, _script = c.split("_", 1)
        idx.setdefault(iso3, []).append(c)
    for k in list(idx.keys()):
        idx[k] = sorted(set(idx[k]))
    return idx


def list_all_iso3_from_nllb_codes(nllb_codes: Sequence[str]) -> List[str]:
    iso3 = []
    for c in nllb_codes:
        if "_" in c:
            iso3.append(c.split("_", 1)[0])
    return sorted(set(iso3))


def _preferred_scripts_for_iso3(iso3: str, original_code: str) -> List[str]:
    """
    Minimal script preferences.
    original_code is what user passed (may be 'bg', 'ru', 'zh-tw', etc.) so we can decide Hans/Hant.
    """
    original_code = (original_code or "").strip().lower()

    if iso3 in ("rus", "ukr", "bul", "srp", "bel", "kaz", "kir", "mkd", "tgk", "mon"):
        return ["Cyrl", "Latn", "Arab"]

    if iso3 in ("arb", "pes", "urd"):
        return ["Arab", "Latn"]

    if iso3 in ("hin", "mar", "nep"):
        return ["Deva", "Latn"]

    if iso3 in ("zho",):
        if original_code in ("zh-tw", "zh-hant"):
            return ["Hant", "Hans"]
        return ["Hans", "Hant"]

    return ["Latn", "Cyrl", "Arab"]


def _to_iso3(code: str) -> str:
    code = (code or "").strip().lower()
    if not code:
        raise ValueError("empty language code")

    # if already iso3
    if len(code) == 3 and code.isalpha():
        return code

    # aliases (iso2, zh-cn, etc.)
    if code in ISO_ALIAS_TO_ISO3:
        return ISO_ALIAS_TO_ISO3[code]

    # last resort: try iso639 library if installed
    try:
        import iso639  # type: ignore

        if hasattr(iso639, "Lang"):
            return iso639.Lang(code).pt3  # type: ignore
        if hasattr(iso639, "languages") and hasattr(iso639.languages, "get"):
            lang = iso639.languages.get(part1=code) or iso639.languages.get(part2b=code) or iso639.languages.get(part3=code)
            if lang and hasattr(lang, "part3"):
                return lang.part3  # type: ignore
    except Exception:
        pass

    raise ValueError(f"cannot convert iso code to iso3: {code}")


def iso_to_nllb(code: str, *, nllb_iso3_index: Dict[str, List[str]]) -> str:
    iso3 = _to_iso3(code)
    variants = nllb_iso3_index.get(iso3) or []
    if not variants:
        raise ValueError(f"language not supported by this NLLB tokenizer: code={code} iso3={iso3}")

    if len(variants) == 1:
        return variants[0]

    prefs = _preferred_scripts_for_iso3(iso3, code)
    for script in prefs:
        for v in variants:
            if v.endswith("_" + script):
                return v

    return variants[0]


def list_iso_langs_supported_by_mapping(nllb_codes: Sequence[str]) -> List[str]:
    """
    Return ALL languages supported by the model in ISO-639-3 form (≈200).
    This matches your requirement "need all".
    """
    return list_all_iso3_from_nllb_codes(nllb_codes)