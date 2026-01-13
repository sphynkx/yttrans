import asyncio
import re
import time
from typing import Optional


_LANG_ALIASES = {
    "he": "iw",
    "he-il": "iw",
    "jv": "jw",
    "fil": "tl",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "mni-mtei": "mni-Mtei",
}


def _apply_alias(code: str) -> str:
    if not code:
        return code
    low = code.strip().lower()
    return _LANG_ALIASES.get(low, code)


def _norm_lang(code: str) -> str:
    if not code:
        return code
    c = code.strip()
    if c == "":
        return c

    c = _apply_alias(c)

    parts = re.split(r"[-_]", c)
    if not parts:
        return c

    parts[0] = parts[0].lower()

    for i in range(1, len(parts)):
        p = parts[i]
        if len(p) == 2 and p.isalpha():
            parts[i] = p.upper()
        elif len(p) == 4 and p.isalpha():
            parts[i] = p.title()
        elif len(p) == 3 and p.isdigit():
            parts[i] = p
        else:
            parts[i] = p

    return "-".join(parts)


def _is_transient_error(e: Exception) -> bool:
    """
    Detect errors that are likely temporary:
    - rate limit / captcha / http 429/503
    - connection reset / timeouts
    deep-translator often raises generic Exception with these messages.
    """
    msg = str(e or "").lower()

    needles = [
        "api connection error",
        "request exception",
        "too many requests",
        "429",
        "503",
        "temporarily",
        "timeout",
        "timed out",
        "connection reset",
        "connection aborted",
        "remote end closed connection",
        "ssl",
        "captcha",
        "rate limit",
        "service unavailable",
        "bad gateway",
        "proxy error",
    ]
    return any(n in msg for n in needles)


class GoogleWebProvider:
    name = "googleweb"

    def __init__(self, cfg):
        self.cfg = cfg

        # QPS throttling across all translate calls in this process.
        # Set googleweb_qps to 0.5..1 for stability.
        qps = float(cfg.get("googleweb_qps") or 0)
        self._min_interval = (1.0 / float(qps)) if qps > 0 else 0.0
        self._last_call_ts = 0.0

        self._retry_attempts = int(cfg.get("googleweb_retry_attempts") or 3)
        self._retry_backoff_sec = float(cfg.get("googleweb_retry_backoff_sec") or 20)

    def list_languages(self):
        whitelist = self.cfg.get("langs") or []
        if whitelist:
            return whitelist

        try:
            try:
                from googletrans.constants import LANGUAGES
            except Exception:
                from googletrans import LANGUAGES

            return sorted(list(LANGUAGES.keys()))
        except Exception:
            return whitelist

    def _throttle(self):
        if self._min_interval <= 0:
            return
        now = time.time()
        dt = now - self._last_call_ts
        if dt < self._min_interval:
            time.sleep(self._min_interval - dt)
        self._last_call_ts = time.time()

    def translate(self, text, src_lang, tgt_lang):
        if text is None:
            return ""
        if text.strip() == "":
            return text

        src_lang = (src_lang or "auto").strip() or "auto"
        if src_lang != "auto":
            src_lang = _norm_lang(src_lang)

        tgt_lang = _norm_lang(tgt_lang)

        # Prefer deep-translator first (often more stable than googletrans)
        order = self.cfg.get("googleweb_order") or ["deep", "googletrans"]

        last_err: Optional[Exception] = None

        # Retry loop only for transient errors.
        # We retry the whole impl chain, because sometimes one impl fails and the other works.
        attempts = max(1, int(self._retry_attempts))
        for attempt in range(1, attempts + 1):
            for impl in order:
                try:
                    self._throttle()

                    if impl == "googletrans":
                        return self._translate_googletrans(text, src_lang, tgt_lang)

                    if impl == "deep":
                        return self._translate_deep(text, src_lang, tgt_lang)

                    last_err = RuntimeError(f"unknown googleweb impl: {impl}")

                except Exception as e:
                    last_err = e
                    # try next impl in chain

            # if we reached here, both impls failed
            if last_err and _is_transient_error(last_err) and attempt < attempts:
                # exponential-ish backoff
                sleep_s = self._retry_backoff_sec * (1 + (attempt - 1) * 0.5)
                time.sleep(sleep_s)
                continue

            break

        raise RuntimeError(f"googleweb translate failed: {last_err}")

    def _translate_deep(self, text, src_lang, tgt_lang):
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source=src_lang, target=tgt_lang).translate(text)

    def _translate_googletrans(self, text, src_lang, tgt_lang):
        from googletrans import Translator

        async def _do():
            tr = Translator()
            res = await tr.translate(text, src=src_lang, dest=tgt_lang)
            return res.text

        timeout = int(self.cfg.get("googleweb_timeout_sec") or 10)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(_do(), loop)
            return fut.result(timeout=timeout)

        return asyncio.run(_do())