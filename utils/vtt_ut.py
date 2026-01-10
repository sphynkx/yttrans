def is_timestamp_line(line):
    return "-->" in line


def translate_vtt(src_vtt, translate_line_fn):
    """
    MVP: Preserve the WEBVTT + structure.
    Translate only the following "text strings" into cue:
    - not empty
    - not a string with '-->'
    - does not start with 'NOTE' (skip as is)
    - copy everything else.
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

        # cue identifiers (often numbers/strings without '-->') — leave as is if the next string is a timestamp?
        # MVP: heuristic — if the string consists only of numbers, consider it an identifier.
        if s.isdigit():
            out.append(raw)
            continue

        out.append(translate_line_fn(raw))
    return "\n".join(out) + ("\n" if src_vtt.endswith("\n") else "")