import re
import uuid


def is_timestamp_line(line):
    return "-->" in line


def extract_translatable_lines(src_vtt):
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
    return f"\n__YTTRANS_SPLIT_{token}__\n"


def _pick_unique_token(texts):
    token = uuid.uuid4().hex[:12]
    hay = "\n".join(texts or [])
    while f"YTTRANS_SPLIT_{token}" in hay:
        token = uuid.uuid4().hex[:12]
    return token


_SENT_BOUNDARY_RE = re.compile(r"(.+?[\.!?…]+)(\s+|$)", flags=re.DOTALL)


def _split_hard_with_space_preference(text: str, max_len: int):
    """
    Always returns chunks <= max_len.
    Prefer splitting on whitespace if possible.
    """
    if max_len <= 0:
        return [text]
    if len(text) <= max_len:
        return [text]

    out = []
    pos = 0
    n = len(text)
    while pos < n:
        end = min(n, pos + max_len)
        window = text[pos:end]

        # prefer last whitespace to avoid breaking words
        cut = window.rfind(" ")
        if cut <= 0:
            cut = len(window)

        out.append(text[pos : pos + cut])
        pos += cut

        # skip leading spaces in next chunk
        while pos < n and text[pos] == " ":
            pos += 1

    return out


def _split_large_text(text: str, max_len: int):
    """
    Split text into chunks <= max_len trying:
      1) sentence boundaries
      2) whitespace
      3) hard cut
    """
    if max_len <= 0:
        return [text]
    if len(text) <= max_len:
        return [text]

    chunks = []
    pos = 0
    n = len(text)

    while pos < n:
        end = min(n, pos + max_len)
        window = text[pos:end]

        # 1) try last sentence boundary within window
        last_end = None
        for m in _SENT_BOUNDARY_RE.finditer(window):
            last_end = m.end()

        if last_end and last_end > 0:
            cut = last_end
            chunks.append(text[pos : pos + cut])
            pos += cut
            continue

        # 2) fallback: split by whitespace preference
        ws_chunks = _split_hard_with_space_preference(text[pos:], max_len)
        chunks.extend(ws_chunks)
        break

    # final safety: ensure all <= max_len
    safe = []
    for ch in chunks:
        if len(ch) <= max_len:
            safe.append(ch)
        else:
            safe.extend(_split_hard_with_space_preference(ch, max_len))

    return safe


def _split_by_delim_token(translated_text: str, token: str):
    pat = re.compile(rf"(?:\s*_{{0,4}})?YTTRANS_SPLIT_{re.escape(token)}(?:_{{0,4}}\s*)?", flags=re.MULTILINE)
    pieces = pat.split(translated_text)
    pieces = [p for p in pieces if p is not None]
    if pieces and pieces[0] == "":
        pieces = pieces[1:]
    if pieces and pieces[-1] == "":
        pieces = pieces[:-1]
    return pieces


def batch_translate_texts(texts, translate_text_fn, max_total_chars=4500):
    if not texts:
        return []

    token = _pick_unique_token(texts)
    delim = _make_delimiter(token)

    joined = delim.join(texts)
    chunks = _split_large_text(joined, max_total_chars)

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