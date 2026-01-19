import logging
import threading
from typing import Optional

log = logging.getLogger("yttrans.madlad400")


class Madlad400Provider:
    name = "madlad400"

    def __init__(self, cfg):
        self.cfg = cfg

        self.max_concurrency = int(cfg.get("madlad400_max_concurrency") or 1)

        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._langs_lock = threading.Lock()

        self._tokenizer = None
        self._model = None
        self._load_err: Optional[Exception] = None

        self._langs_cache = None           # list[str] (no <2...>)
        self._tgt_token_cache = {}         # tgt_lang -> "<2...>"

    def get_meta(self):
        return {
            "engine": self.name,
            "model": (self.cfg.get("madlad400_model") or "").strip(),
            "device": (self.cfg.get("madlad400_device") or "").strip(),
        }

    def warmup(self):
        self._ensure_loaded()
        try:
            _ = self.translate(text="Hello", src_lang="en", tgt_lang="ru")
        except Exception:
            log.exception("warmup translate failed")

    def _ensure_tokenizer_only(self):
        if self._tokenizer is not None:
            return
        with self._load_lock:
            if self._tokenizer is not None:
                return
            model_id = (self.cfg.get("madlad400_model") or "google/madlad400-3b-mt").strip()
            from transformers import AutoTokenizer

            log.info("%s loading tokenizer (no model) model_id=%s", self.name, model_id)
            self._tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)

    @staticmethod
    def _is_lang_token(tok: str) -> bool:
        if not tok.startswith("<2") or not tok.endswith(">"):
            return False
        inner = tok[2:-1]
        if not inner:
            return False
        if inner in ("translate", "transliterate", "back_translated"):
            return False

        # Exclude pure script/region tags (keep language tags like ru_Latn).
        if inner in (
            "Arab", "Armn", "Beng", "Cans", "Cher", "Cyrl", "Deva", "Ethi", "Geor", "Grek",
            "Gujr", "Guru", "Hans", "Hant", "Hebr", "Jpan", "Khmr", "Knda", "Kore", "Latn",
            "Mlym", "Mymr", "Orya", "Taml", "Telu", "Tfng", "Thaa", "Thai", "Tibt",
            "CA", "IR", "NL", "RU", "ZW",
        ):
            return False

        return True

    def list_languages(self):
        if self._langs_cache is not None:
            return self._langs_cache

        with self._langs_lock:
            if self._langs_cache is not None:
                return self._langs_cache

            self._ensure_tokenizer_only()
            vocab = self._tokenizer.get_vocab()

            langs = []
            for tok in vocab.keys():
                if self._is_lang_token(tok):
                    langs.append(tok[2:-1])

            langs = sorted(set(langs))
            self._langs_cache = langs
            return langs

    def _pick_tgt_token(self, tgt_lang: str) -> str:
        if not tgt_lang:
            raise RuntimeError("tgt_lang is required")

        if tgt_lang in self._tgt_token_cache:
            return self._tgt_token_cache[tgt_lang]

        self._ensure_tokenizer_only()
        vocab = self._tokenizer.get_vocab()

        raw = str(tgt_lang).strip()
        c1 = raw.replace("-", "_")

        candidates = [c1, c1.lower(), c1.upper()]
        if "_" in c1:
            a, b = c1.split("_", 1)
            candidates.append(f"{a.lower()}_{b.upper()}")

        for c in candidates:
            tok = f"<2{c}>"
            if tok in vocab and self._is_lang_token(tok):
                self._tgt_token_cache[tgt_lang] = tok
                return tok

        raise RuntimeError(f"unsupported tgt_lang={tgt_lang}: no matching <2...> token found")

    def _ensure_loaded(self):
        if self._model is not None and self._tokenizer is not None:
            return
        if self._load_err is not None:
            raise RuntimeError(f"{self.name} load failed: {self._load_err}")

        with self._load_lock:
            if self._model is not None and self._tokenizer is not None:
                return
            if self._load_err is not None:
                raise RuntimeError(f"{self.name} load failed: {self._load_err}")

            model_id = (self.cfg.get("madlad400_model") or "google/madlad400-3b-mt").strip()
            device = (self.cfg.get("madlad400_device") or "cpu").strip()

            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

                torch_threads = int(self.cfg.get("madlad400_torch_threads") or 0)
                if torch_threads > 0:
                    torch.set_num_threads(torch_threads)

                if self._tokenizer is None:
                    log.info("%s loading tokenizer model_id=%s", self.name, model_id)
                    self._tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)

                log.info("%s loading model model_id=%s", self.name, model_id)
                self._model = AutoModelForSeq2SeqLM.from_pretrained(model_id)
                self._model.eval()

                dev_l = device.lower()
                if dev_l == "cpu":
                    self._model.to("cpu")
                else:
                    if torch.cuda.is_available():
                        self._model.to(device)
                    else:
                        log.warning("%s device=%s requested but cuda not available; using cpu", self.name, device)
                        self._model.to("cpu")

                log.info("%s model ready device=%s", self.name, device)

            except Exception as e:
                self._load_err = e
                raise

    def translate_batch(self, texts, src_lang, tgt_lang):
        if not texts:
            return []

        self._ensure_loaded()

        max_input_tokens = int(self.cfg.get("madlad400_max_input_tokens") or 512)
        max_new_tokens = int(self.cfg.get("madlad400_max_new_tokens") or 256)
        num_beams = int(self.cfg.get("madlad400_num_beams") or 1)
        batch_size = int(self.cfg.get("madlad400_batch_size") or 1)

        tgt_tok = self._pick_tgt_token(tgt_lang)

        out = []
        i = 0

        with self._infer_lock:
            while i < len(texts):
                batch = texts[i : i + batch_size]
                i += batch_size

                prompts = [f"{tgt_tok}{t or ''}" for t in batch]

                inputs = self._tokenizer(
                    prompts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=max_input_tokens,
                )

                try:
                    model_dev = next(self._model.parameters()).device
                    inputs = {k: v.to(model_dev) for k, v in inputs.items()}
                except Exception:
                    inputs = {k: v.to("cpu") for k, v in inputs.items()}

                import torch
                with torch.no_grad():
                    gen = self._model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        num_beams=num_beams,
                        early_stopping=False,
                    )

                decoded = self._tokenizer.batch_decode(gen, skip_special_tokens=True)
                out.extend(decoded)

        return out

    def translate(self, text, src_lang, tgt_lang):
        if text is None:
            return ""
        if text.strip() == "":
            return text
        res = self.translate_batch([text], src_lang=src_lang, tgt_lang=tgt_lang)
        return res[0] if res else ""