import threading
from typing import Optional


class Fbm2m100Provider:
    name = "fbm2m100"

    def __init__(self, cfg):
        self.cfg = cfg
        self._lock = threading.Lock()

        self._tokenizer = None
        self._model = None
        self._load_err: Optional[Exception] = None

        self._langs_cache = None
        self._langs_lock = threading.Lock()

    def warmup(self):
        self._ensure_loaded()

    def list_languages(self):
        whitelist = self.cfg.get("langs") or []
        if whitelist:
            return whitelist
        return self._list_languages_all()

    def _list_languages_all(self):
        if self._langs_cache is not None:
            return self._langs_cache

        with self._langs_lock:
            if self._langs_cache is not None:
                return self._langs_cache

            model_id = (self.cfg.get("fbm2m100_model") or "facebook/m2m100_418M").strip()

            try:
                from transformers import AutoTokenizer

                tok = AutoTokenizer.from_pretrained(model_id)

                langs = []
                if hasattr(tok, "lang_code_to_id") and isinstance(tok.lang_code_to_id, dict):
                    langs = sorted(tok.lang_code_to_id.keys())

                self._langs_cache = langs
                return langs
            except Exception:
                self._langs_cache = []
                return []

    def _ensure_loaded(self):
        if self._model is not None and self._tokenizer is not None:
            return
        if self._load_err is not None:
            raise RuntimeError(f"fbm2m100 load failed: {self._load_err}")

        with self._lock:
            if self._model is not None and self._tokenizer is not None:
                return
            if self._load_err is not None:
                raise RuntimeError(f"fbm2m100 load failed: {self._load_err}")

            model_id = (self.cfg.get("fbm2m100_model") or "facebook/m2m100_418M").strip()
            device = (self.cfg.get("fbm2m100_device") or "cpu").strip().lower()

            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

                torch_threads = int(self.cfg.get("fbm2m100_torch_threads") or 0)
                if torch_threads > 0:
                    torch.set_num_threads(torch_threads)

                # keep CPU-only predictable for now
                if device != "cpu":
                    device = "cpu"

                self._tokenizer = AutoTokenizer.from_pretrained(model_id)
                self._model = AutoModelForSeq2SeqLM.from_pretrained(model_id)
                self._model.to(device)
                self._model.eval()

            except Exception as e:
                self._load_err = e
                raise

    def _get_forced_bos_id(self, tgt_lang: str) -> int:
        try:
            return self._tokenizer.get_lang_id(tgt_lang)
        except Exception as e:
            raise RuntimeError(f"fbm2m100 unsupported target language: {tgt_lang}: {e}")

    def _set_src_lang(self, src_lang: str):
        if src_lang and src_lang != "auto":
            try:
                self._tokenizer.src_lang = src_lang
            except Exception:
                pass

    def _translate_texts_batched(self, texts, src_lang, tgt_lang):
        """
        Core batched translation. texts: list[str]
        Returns list[str] (same length).
        """
        if not texts:
            return []

        self._ensure_loaded()

        src_lang = (src_lang or "auto").strip() or "auto"
        tgt_lang = (tgt_lang or "").strip()
        if not tgt_lang:
            raise RuntimeError("tgt_lang is required")

        forced_id = self._get_forced_bos_id(tgt_lang)
        self._set_src_lang(src_lang)

        import torch

        # config
        max_input_tokens = int(self.cfg.get("fbm2m100_max_input_tokens") or 1024)
        max_new_tokens = int(self.cfg.get("fbm2m100_max_new_tokens") or 256)
        num_beams = int(self.cfg.get("fbm2m100_num_beams") or 1)
        batch_size = int(self.cfg.get("fbm2m100_batch_size") or 8)

        out_texts = []
        i = 0
        n = len(texts)

        while i < n:
            batch = texts[i : i + batch_size]
            i += batch_size

            # truncation protects against >1024 indexing errors
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

            decoded = self._tokenizer.batch_decode(out, skip_special_tokens=True)
            out_texts.extend(decoded)

        return out_texts

    def _split_long_text_by_tokens(self, text: str, max_input_tokens: int):
        """
        Token-aware split to avoid truncation losing tail.
        Strategy:
          - encode without special tokens
          - slice token ids into chunks
          - decode chunks back to text
        """
        if not text:
            return [""]

        # Note: use tokenizer directly; keep it simple
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
        """
        Public batch API:
          - preserves 1:1 mapping (no delimiter issues)
          - token-aware splitting for very long lines
        """
        if not texts:
            return []

        self._ensure_loaded()

        max_input_tokens = int(self.cfg.get("fbm2m100_max_input_tokens") or 1024)

        # expand long lines into multiple segments
        # mapping: original index -> list of segment indices in expanded list
        expanded = []
        mapping = []
        for t in texts:
            parts = self._split_long_text_by_tokens(t, max_input_tokens=max_input_tokens)
            start = len(expanded)
            expanded.extend(parts)
            mapping.append((start, len(expanded)))

        translated_expanded = self._translate_texts_batched(expanded, src_lang=src_lang, tgt_lang=tgt_lang)

        # merge segments back
        out = []
        for start, end in mapping:
            merged = "".join(translated_expanded[start:end])
            out.append(merged)

        return out

    def translate(self, text, src_lang, tgt_lang):
        """
        Single-text API used by fallback line_by_line and other code paths.
        Implemented via translate_batch for consistency.
        """
        if text is None:
            return ""
        if text.strip() == "":
            return text

        res = self.translate_batch([text], src_lang=src_lang, tgt_lang=tgt_lang)
        return res[0] if res else ""