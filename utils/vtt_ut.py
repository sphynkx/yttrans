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

        # cue identifier heuristic
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

    src_ended_with_nl = False
    # we can't know original trailing newline after splitlines(); caller can pass flag if needed.
    # Keep previous behavior: if original vtt ended with '\n', add it back in caller. Here return join only.
    return "\n".join(out)


def _pick_unique_delimiter(texts):
    # delimiter should be unlikely to appear in captions
    # make it job-unique
    token = uuid.uuid4().hex[:12]
    delim = f"\n<<<YTTRANS_SPLIT_{token}>>>\n"

    hay = "\n".join(texts or [])
    while delim.strip() in hay:
        token = uuid.uuid4().hex[:12]
        delim = f"\n<<<YTTRANS_SPLIT_{token}>>>\n"
    return delim


_SENT_BOUNDARY_RE = re.compile(r"(.+?[\.!?…]+)(\s+|$)", flags=re.DOTALL)


def _split_large_text_by_sentence(text, max_len):
    """
    Splits a big text into chunks <= max_len trying to break on sentence boundaries.
    If cannot (very long sentence), hard-splits.
    """
    if len(text) <= max_len:
        return [text]

    parts = []
    pos = 0
    n = len(text)

    while pos < n:
        # take window up to max_len
        window = text[pos : min(n, pos + max_len)]

        # find last sentence boundary inside window
        last_end = None
        for m in _SENT_BOUNDARY_RE.finditer(window):
            last_end = m.end()

        if last_end is None or last_end < 1:
            # no boundary: hard split
            cut = len(window)
        else:
            cut = last_end

        chunk = text[pos : pos + cut]
        parts.append(chunk)
        pos += cut

    return parts


def batch_translate_texts(texts, translate_text_fn, max_total_chars=8000):
    """
    texts: list[str] - individual cue lines (already selected)
    translate_text_fn: callable(text)->translated_text for whole block
    Returns translated_texts list with same length.

    Strategy:
      - join with unique delimiter
      - if very big: chunk joined text by sentence boundaries (.) (!) (?) (…) (…)
      - translate chunk-by-chunk
      - split by delimiter back
      - strict count check
    """
    if not texts:
        return []

    delim = _pick_unique_delimiter(texts)
    joined = delim.join(texts)

    chunks = _split_large_text_by_sentence(joined, max_total_chars)

    translated_joined = ""
    for ch in chunks:
        translated_joined += translate_text_fn(ch)

    # Now split back. We expect delimiter preserved exactly.
    pieces = translated_joined.split(delim)

    if len(pieces) != len(texts):
        raise ValueError(
            "delimiter split mismatch after translation: "
            f"got {len(pieces)} pieces expected {len(texts)}. "
            "Likely translator modified delimiter."
        )

    return pieces


def translate_vtt(src_vtt, translate_line_fn):
    """
    Backward-compatible old function: line-by-line translation.
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