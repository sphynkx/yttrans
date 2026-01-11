import re
import uuid


def is_timestamp_line(line):
    return "-->" in line


def extract_translatable_lines(src_vtt):
    """
    Returns:
      lines: all original lines (list[str])
      idxs: indexes in lines which should be translated
      texts: the original texts at those indexes
    """
    if src_vtt is None:
        return [], [], []

    lines = src_vtt.splitlines()
    idxs = []
    texts = []

    for i, raw in enumerate(lines):
        s = raw.strip()

        if s == "" or is_timestamp_line(s) or s == "WEBVTT" or s.startswith("NOTE"):
            continue

        if s.isdigit():
            continue

        idxs.append(i)
        texts.append(raw)

    return lines, idxs, texts


def inject_translated_lines(lines, idxs, translated_texts):
    if len(idxs) != len(translated_texts):
        raise ValueError(f"translated lines count mismatch: {len(translated_texts)} != {len(idxs)}")

    out = list(lines)
    for i, t in zip(idxs, translated_texts):
        out[i] = t

    return "\n".join(out)


def _make_delimiter(token: str) -> str:
    # ASCII-only delimiter, less likely to be “beautified” in RTL languages
    return f"\n__YTTRANS_SPLIT_{token}__\n"


def _pick_unique_token(texts):
    token = uuid.uuid4().hex[:12]
    hay = "\n".join(texts or [])
    while f"YTTRANS_SPLIT_{token}" in hay:
        token = uuid.uuid4().hex[:12]
    return token


_SENT_BOUNDARY_RE = re.compile(r"(.+?[\.!?…]+)(\s+|$)", flags=re.DOTALL)


def _split_large_text_by_sentence(text, max_len):
    if max_len <= 0:
        return [text]
    if len(text) <= max_len:
        return [text]

    parts = []
    pos = 0
    n = len(text)

    while pos < n:
        window = text[pos : min(n, pos + max_len)]

        last_end = None
        for m in _SENT_BOUNDARY_RE.finditer(window):
            last_end = m.end()

        cut = last_end if last_end and last_end > 0 else len(window)
        parts.append(text[pos : pos + cut])
        pos += cut

    return parts


def _split_by_delim_token(translated_text: str, token: str):
    """
    Split translated text by a delimiter token, tolerant to whitespace/newlines.
    We search for the token string itself, allowing optional underscores/newlines around it.
    """
    # We will split on occurrences of "YTTRANS_SPLIT_<token>" with surrounding underscores/spaces/newlines.
    # Example delimiter originally: "\n__YTTRANS_SPLIT_abcd__\n"
    pat = re.compile(rf"(?:\s*_{{0,4}})?YTTRANS_SPLIT_{re.escape(token)}(?:_{{0,4}}\s*)?", flags=re.MULTILINE)

    # re.split keeps order; it will drop the separators
    pieces = pat.split(translated_text)

    # However, pat also matches inside delimiter with underscores; splitting may produce extra empty pieces.
    pieces = [p for p in pieces if p is not None]

    # Trim only *one* leading/trailing empties if produced by separators at boundaries
    if pieces and pieces[0] == "":
        pieces = pieces[1:]
    if pieces and pieces[-1] == "":
        pieces = pieces[:-1]

    return pieces


def batch_translate_texts(texts, translate_text_fn, max_total_chars=8000):
    if not texts:
        return []

    token = _pick_unique_token(texts)
    delim = _make_delimiter(token)

    joined = delim.join(texts)
    chunks = _split_large_text_by_sentence(joined, max_total_chars)

    translated_joined = ""
    for ch in chunks:
        translated_joined += translate_text_fn(ch)

    pieces = _split_by_delim_token(translated_joined, token)

    if len(pieces) != len(texts):
        raise ValueError(
            "delimiter split mismatch after translation: "
            f"got {len(pieces)} pieces expected {len(texts)}. "
            "Likely translator modified delimiter."
        )

    return pieces


def translate_vtt(src_vtt, translate_line_fn):
    """
    Legacy line-by-line translation.
    """
    if src_vtt is None:
        return ""

    lines = src_vtt.splitlines()
    out = []
    for line in lines:
        raw = line
        s = line.strip()

        if s == "" or is_timestamp_line(s) or s == "WEBVTT" or s.startswith("NOTE"):
            out.append(raw)
            continue

        if s.isdigit():
            out.append(raw)
            continue

        out.append(translate_line_fn(raw))

    return "\n".join(out) + ("\n" if src_vtt.endswith("\n") else "")