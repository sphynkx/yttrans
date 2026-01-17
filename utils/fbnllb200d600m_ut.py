from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

# NLLB language codes are in tokenizer.additional_special_tokens like:
#   eng_Latn, rus_Cyrl, zho_Hans, zho_Hant, ...
_NLLB_CODE_RE = re.compile(r"^[a-z]{3}_[A-Za-z]{4}$")
_SAFE_UI_CODE_RE = re.compile(r"^[a-z0-9\-]+$")


def extract_nllb_lang_codes(tokenizer) -> List[str]:
    """
    Extract NLLB codes from tokenizer additional_special_tokens.
    Returns e.g. ["eng_Latn","rus_Cyrl",...]
    """
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
            # Strictly keep tokens that look like NLLB codes
            codes.append(t)

    return sorted(set(codes))


def build_iso3_index(nllb_codes: Sequence[str]) -> Dict[str, List[str]]:
    """
    iso3 -> list of NLLB variants
    e.g. "zho" -> ["zho_Hans","zho_Hant"]
    """
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
        iso3.append(c.split("_", 1)[0])
    return sorted(set(iso3))


def _iso2_from_iso3_pycountry(iso3: str) -> Optional[str]:
    """
    Convert ISO-639-3 -> ISO-639-1 using pycountry.
    Returns None if ISO-639-1 doesn't exist.
    """
    iso3 = (iso3 or "").strip().lower()
    if len(iso3) != 3 or not iso3.isalpha():
        return None

    # Special NLLB codes that are not plain ISO-639-3 in the usual sense
    # (NLLB uses macrolanguage-ish codes for some):
    special = {
        "arb": "ar",  # Arabic (Standard)
        "pes": "fa",  # Persian
        "zsm": "ms",  # Malay
    }
    if iso3 in special:
        return special[iso3]

    try:
        import pycountry  # type: ignore

        lang = pycountry.languages.get(alpha_3=iso3)
        if not lang:
            return None
        a2 = getattr(lang, "alpha_2", None)
        if isinstance(a2, str) and a2:
            return a2.lower()
        return None
    except Exception:
        return None


def _normalize_to_iso3(code: str) -> str:
    """
    Accept:
      - iso2: ru
      - iso3: rus
      - bcp47-ish: zh-cn / zh-tw
    Return iso3.
    """
    code = (code or "").strip().lower()
    if not code:
        raise ValueError("empty language code")

    # keep as tags for UI, but internally map them to zho
    if code in ("zh-cn", "zh-hans"):
        return "zho"
    if code in ("zh-tw", "zh-hant"):
        return "zho"

    if len(code) == 3 and code.isalpha():
        return code

    # Try pycountry for iso2->iso3
    try:
        import pycountry  # type: ignore

        if len(code) == 2 and code.isalpha():
            lang = pycountry.languages.get(alpha_2=code)
            if lang and getattr(lang, "alpha_3", None):
                return str(lang.alpha_3).lower()
    except Exception:
        pass

    # Special fallback for common mismatches / NLLB specifics
    fallback = {
        "ar": "arb",
        "fa": "pes",
        "ms": "zsm",
        "zh": "zho",
    }
    if code in fallback:
        return fallback[code]

    raise ValueError(f"cannot convert code to iso3: {code}")


def _preferred_scripts_for_iso3(iso3: str, original_code: str) -> List[str]:
    """
    Minimal script preferences when iso3 has multiple scripts in NLLB.
    This is not about language existence; only choosing among variants.
    """
    original_code = (original_code or "").strip().lower()

    if iso3 in ("rus", "ukr", "bul", "srp", "bel", "kaz", "kir", "mkd", "tgk", "mon"):
        return ["Cyrl", "Latn", "Arab"]

    if iso3 in ("arb", "pes", "urd"):
        return ["Arab", "Latn"]

    if iso3 in ("hin", "mar", "nep"):
        return ["Deva", "Latn"]

    if iso3 == "zho":
        if original_code in ("zh-tw", "zh-hant"):
            return ["Hant", "Hans"]
        return ["Hans", "Hant"]

    # default preference
    return ["Latn", "Cyrl", "Arab"]


def iso_to_nllb(code: str, *, nllb_iso3_index: Dict[str, List[str]]) -> str:
    """
    Map user/service code (iso2/iso3/zh-cn/zh-tw) to the NLLB code token.
    """
    iso3 = _normalize_to_iso3(code)
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


def list_ui_langs_from_nllb_codes(nllb_codes: Sequence[str]) -> List[str]:
    """
    Return ALL supported languages (~200) as hybrid codes:
      - iso2 where it exists
      - else iso3
    No duplicates.
    Safe for filenames (letters/digits/hyphen only).
    """
    iso3_list = list_all_iso3_from_nllb_codes(nllb_codes)

    out = []
    for iso3 in iso3_list:
        iso2 = _iso2_from_iso3_pycountry(iso3)
        out.append(iso2 if iso2 else iso3)

    # Expose both Chinese variants explicitly (optional but useful for UI)
    # Keep them as tags, still safe for filenames.
    if "zh" in out:
        out = [x for x in out if x != "zh"]
        out.extend(["zh", "zh-cn", "zh-tw"])

    # sanitize + dedupe
    safe = []
    for x in out:
        x = (x or "").strip().lower()
        if x and _SAFE_UI_CODE_RE.fullmatch(x):
            safe.append(x)

    return sorted(set(safe))