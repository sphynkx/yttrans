class DummyProvider:
    name = "dummy"

    def __init__(self, cfg):
        self.cfg = cfg

    def list_languages(self):
        # fallback to config langs
        return self.cfg.get("langs") or ["en"]

    def translate(self, text, src_lang, tgt_lang):
        if text is None:
            return ""
        if text.strip() == "":
            return text

        prefix = text[: len(text) - len(text.lstrip(" "))]
        suffix = text[len(text.rstrip(" ")) :]

        core = text.strip()
        if core.isdigit():
            return text

        return f"{prefix}[{tgt_lang}] Lorem ipsum{suffix}"