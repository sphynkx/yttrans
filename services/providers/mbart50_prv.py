import logging
import threading
from typing import Optional

log = logging.getLogger("yttrans.mbart50")


# Minimal mapping from common app language codes -> mBART50 language codes.
# You can extend as needed. If app already sends mbart codes (e.g. "ru_RU"),
# provider will accept them directly.
_MBART50_COMMON_MAP = {
    "en": "en_XX",
    "ru": "ru_RU",
    "uk": "uk_UA",
    "fr": "fr_XX",
    "de": "de_DE",
    "es": "es_XX",
    "it": "it_IT",
    "pt": "pt_XX",
    "nl": "nl_XX",
    "pl": "pl_PL",
    "tr": "tr_TR",
    "ar": "ar_AR",
    "he": "he_IL",
    "hi": "hi_IN",
    "id": "id_ID",
    "ja": "ja_XX",
    "ko": "ko_KR",
    "zh": "zh_CN",
}


def _norm_lang(x: str) -> str:
    x = (x or "").strip()
    if not x:
        return ""
    x = x.replace("_", "-").lower()
    # keep region if present: pt-br -> pt-br
    return x


def _to_mbart50_code(x: str, lang_code_to_id: dict) -> str:
    """
    Accepts:
      - "ru" -> "ru_RU"
      - "fr-FR"/"fr" -> "fr_XX" (mBART doesn't distinguish FR/XX for many langs)
      - already mbart code "ru_RU" -> "ru_RU"
    """
    if not x:
        return ""

    raw = (x or "").strip()
    # if user already passed mbart code
    if raw in lang_code_to_id:
        return raw

    n = _norm_lang(raw)

    # try common map by base lang
    base = n.split("-", 1)[0]
    mapped = _MBART50_COMMON_MAP.get(base)
    if mapped and mapped in lang_code_to_id:
        return mapped

    # try to convert xx-yy -> xx_YY and test
    if "-" in n:
        a, b = n.split("-", 1)
        cand = f"{a.lower()}_{b.upper()}"
        if cand in lang_code_to_id:
            return cand

    # last resort: if base itself like "en" isn't found, fail
    return ""


class Mbart50Provider:
    name = "mbart50"

    def __init__(self, cfg):
        self.cfg = cfg
        self.max_concurrency = int(cfg.get("mbart50_max_concurrency") or 1)

        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._langs_lock = threading.Lock()

        self._tokenizer = None
        self._model = None
        self._load_err: Optional[Exception] = None

        self._langs_cache = None  # list[str] of mbart codes

    def get_meta(self):
        return {
            "engine": self.name,
            "model": (self.cfg.get("mbart50_model") or "").strip(),
            "device": (self.cfg.get("mbart50_device") or "").strip(),
        }

    def _ensure_tokenizer_only(self):
        if self._tokenizer is not None:
            return
        with self._load_lock:
            if self._tokenizer is not None:
                return
            model_id = (self.cfg.get("mbart50_model") or "").strip()
            from transformers import AutoTokenizer

            log.info("%s loading tokenizer (no model) model_id=%s", self.name, model_id)
            self._tokenizer = AutoTokenizer.from_pretrained(model_id, use_fast=True)

    def list_languages(self):
        """
        Full list from tokenizer.lang_code_to_id.
        Returns mBART language codes (e.g. ru_RU, en_XX).
        """
        if self._langs_cache is not None:
            return self._langs_cache

        with self._langs_lock:
            if self._langs_cache is not None:
                return self._langs_cache

            self._ensure_tokenizer_only()

            lang_map = getattr(self._tokenizer, "lang_code_to_id", None)
            if not isinstance(lang_map, dict) or not lang_map:
                # very unexpected for mBART; but keep service alive
                self._langs_cache = []
                return self._langs_cache

            langs = sorted(lang_map.keys())
            self._langs_cache = langs
            return langs

    def warmup(self):
        self._ensure_loaded()
        try:
            _ = self.translate(text="Hello", src_lang="en", tgt_lang="ru")
        except Exception:
            log.exception("warmup translate failed")

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

            model_id = (self.cfg.get("mbart50_model") or "facebook/mbart-large-50-many-to-many-mmt").strip()
            device = (self.cfg.get("mbart50_device") or "cpu").strip()

            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

                torch_threads = int(self.cfg.get("mbart50_torch_threads") or 0)
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

        max_input_tokens = int(self.cfg.get("mbart50_max_input_tokens") or 512)
        max_new_tokens = int(self.cfg.get("mbart50_max_new_tokens") or 256)
        num_beams = int(self.cfg.get("mbart50_num_beams") or 1)
        batch_size = int(self.cfg.get("mbart50_batch_size") or 1)

        lang_map = getattr(self._tokenizer, "lang_code_to_id", None)
        if not isinstance(lang_map, dict) or not lang_map:
            raise RuntimeError("mbart50 tokenizer has no lang_code_to_id")

        src_code = _to_mbart50_code(src_lang, lang_map) or "en_XX"
        tgt_code = _to_mbart50_code(tgt_lang, lang_map)
        if not tgt_code:
            raise RuntimeError(f"unsupported tgt_lang={tgt_lang} for mbart50")

        forced_bos = lang_map.get(tgt_code)
        if forced_bos is None:
            raise RuntimeError(f"cannot resolve forced_bos_token_id for {tgt_code}")

        out = []
        i = 0

        with self._infer_lock:
            while i < len(texts):
                batch = texts[i : i + batch_size]
                i += batch_size

                # mBART: set source language before tokenization
                self._tokenizer.src_lang = src_code

                inputs = self._tokenizer(
                    batch,
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
                        forced_bos_token_id=forced_bos,
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