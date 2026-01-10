class DeepLProvider:
    name = "deepl"

    def __init__(self, cfg):
        self.cfg = cfg

    def list_languages(self):
        return self.cfg.get("langs") or []

    def translate(self, text, src_lang, tgt_lang):
        raise RuntimeError("deepl provider is not implemented in MVP (use YTTRANS_ENGINE=dummy)")