import threading
from typing import Optional

from utils.fbnllb200d600m_ut import (
    build_iso3_index,
    extract_nllb_lang_codes,
    iso_to_nllb,
    list_iso_langs_supported_by_mapping,
)


class Fbnllb200d600mProvider:
    name = "fbnllb200d600m"

    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()

        self._tokenizer = None
        self._model = None
        self._load_err: Optional[Exception] = None

        self._langs_cache = None
        self._langs_lock = threading.Lock()

        self._nllb_codes_cache = None
        self._iso3_index_cache = None

    def warmup(self):
        self._ensure_loaded()

    def list_languages(self):
        # if global whitelist configured - respect it
        whitelist = self.cfg.get("langs") or []
        if whitelist:
            supported = set(self._list_languages_all())
            return [x for x in whitelist if x in supported]
        return self._list_languages_all()

    def _ensure_tokenizer_codes(self):
        if self._nllb_codes_cache is not None and self._iso3_index_cache is not None:
            return

        model_id = (self.cfg.get("fbnllb200d600m_model") or "facebook/nllb-200-distilled-600M").strip()
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(model_id)
        codes = extract_nllb_lang_codes(tok)

        self._nllb_codes_cache = codes
        self._iso3_index_cache = build_iso3_index(codes)

    def _list_languages_all(self):
        if self._langs_cache is not None:
            return self._langs_cache

        with self._langs_lock:
            if self._langs_cache is not None:
                return self._langs_cache

            try:
                self._ensure_tokenizer_codes()
                iso_langs = list_iso_langs_supported_by_mapping(self._nllb_codes_cache or [])
                self._langs_cache = iso_langs
                return iso_langs
            except Exception:
                self._langs_cache = []
                return []

    def _ensure_loaded(self):
        if self._model is not None and self._tokenizer is not None:
            return
        if self._load_err is not None:
            raise RuntimeError(f"fbnllb200d600m load failed: {self._load_err}")

        with self._lock:
            if self._model is not None and self._tokenizer is not None:
                return
            if self._load_err is not None:
                raise RuntimeError(f"fbnllb200d600m load failed: {self._load_err}")

            model_id = (self.cfg.get("fbnllb200d600m_model") or "facebook/nllb-200-distilled-600M").strip()
            device = (self.cfg.get("fbnllb200d600m_device") or "cpu").strip().lower()

            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

                torch_threads = int(self.cfg.get("fbnllb200d600m_torch_threads") or 0)
                if torch_threads > 0:
                    torch.set_num_threads(torch_threads)

                if device != "cpu":
                    device = "cpu"

                self._tokenizer = AutoTokenizer.from_pretrained(model_id)
                self._model = AutoModelForSeq2SeqLM.from_pretrained(model_id)
                self._model.to(device)
                self._model.eval()

                # build caches for iso->nllb conversion
                self._nllb_codes_cache = extract_nllb_lang_codes(self._tokenizer)
                self._iso3_index_cache = build_iso3_index(self._nllb_codes_cache)

            except Exception as e:
                self._load_err = e
                raise

    def _split_long_text_by_tokens(self, text: str, max_input_tokens: int):
        if not text:
            return [""]

        ids = self._tokenizer.encode(text, add_special_tokens=False)
        if len(ids) <= max_input_tokens:
            return [text]

        chunks = []
        pos = 0
        while pos < len(ids):
            part_ids = ids[pos : pos + max_input_tokens]
            pos += max_input_tokens
            part_txt = self._tokenizer.decode(part_ids, skip_special_tokens=True)
            chunks.append(part_txt)

        return chunks

    def translate_batch(self, texts, src_lang, tgt_lang):
        if not texts:
            return []

        self._ensure_loaded()

        src_iso = (src_lang or "auto").strip().lower() or "auto"
        tgt_iso = (tgt_lang or "").strip().lower()
        if not tgt_iso:
            raise RuntimeError("tgt_lang is required")

        # If client passes auto, default to English.
        if src_iso == "auto":
            src_iso = "en"

        iso3_index = self._iso3_index_cache or {}

        src_nllb = iso_to_nllb(src_iso, nllb_iso3_index=iso3_index)
        tgt_nllb = iso_to_nllb(tgt_iso, nllb_iso3_index=iso3_index)

        import torch

        max_input_tokens = int(self.cfg.get("fbnllb200d600m_max_input_tokens") or 1024)
        max_new_tokens = int(self.cfg.get("fbnllb200d600m_max_new_tokens") or 256)
        num_beams = int(self.cfg.get("fbnllb200d600m_num_beams") or 1)
        batch_size = int(self.cfg.get("fbnllb200d600m_batch_size") or 8)

        # token-aware splitting for very long lines
        expanded = []
        mapping = []
        for t in texts:
            parts = self._split_long_text_by_tokens(t, max_input_tokens=max_input_tokens)
            start = len(expanded)
            expanded.extend(parts)
            mapping.append((start, len(expanded)))

        try:
            self._tokenizer.src_lang = src_nllb
        except Exception:
            pass

        forced_id = self._tokenizer.convert_tokens_to_ids(tgt_nllb)

        out_texts = []
        i = 0
        n = len(expanded)
        while i < n:
            batch = expanded[i : i + batch_size]
            i += batch_size

            inputs = self._tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_input_tokens,
            )
            inputs = {k: v.to("cpu") for k, v in inputs.items()}

            with torch.no_grad():
                out = self._model.generate(
                    **inputs,
                    forced_bos_token_id=forced_id,
                    max_new_tokens=max_new_tokens,
                    num_beams=num_beams,
                    early_stopping=False,
                )

            out_texts.extend(self._tokenizer.batch_decode(out, skip_special_tokens=True))

        # merge segments back
        merged = []
        for start, end in mapping:
            merged.append("".join(out_texts[start:end]))

        return merged

    def translate(self, text, src_lang, tgt_lang):
        if text is None:
            return ""
        if text.strip() == "":
            return text
        res = self.translate_batch([text], src_lang=src_lang, tgt_lang=tgt_lang)
        return res[0] if res else ""