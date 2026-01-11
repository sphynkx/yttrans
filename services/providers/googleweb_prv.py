import asyncio
import re
import time


def _norm_lang(code: str) -> str:
    """
    Normalize language code for providers:
    - keep simple 'en', 'ru'
    - convert 'zh-cn' -> 'zh-CN'
    - convert bcp47-ish 'pt-br' -> 'pt-BR'
    - convert script tags 'mni-mtei' -> 'mni-Mtei'
    """
    if not code:
        return code
    c = code.strip()
    if c == "":
        return c

    # common aliases / special cases
    low = c.lower()
    if low == "zh-cn":
        return "zh-CN"
    if low == "zh-tw":
        return "zh-TW"
    if low == "mni-mtei":
        return "mni-Mtei"

    # split by '-' or '_'
    parts = re.split(r"[-_]", c)
    if not parts:
        return c

    # language
    parts[0] = parts[0].lower()

    # remaining: region (2 letters or 3 digits) -> upper, script (4 letters) -> Title
    for i in range(1, len(parts)):
        p = parts[i]
        if len(p) == 2 and p.isalpha():
            parts[i] = p.upper()
        elif len(p) == 4 and p.isalpha():
            parts[i] = p.title()
        elif len(p) == 3 and p.isdigit():
            parts[i] = p
        else:
            # leave as-is but prefer original case? we'll keep as-is
            parts[i] = p

    return "-".join(parts)


class GoogleWebProvider:
    name = "googleweb"

    def __init__(self, cfg):
        self.cfg = cfg
        qps = int(cfg.get("googleweb_qps") or 0)
        self._min_interval = (1.0 / float(qps)) if qps > 0 else 0.0
        self._last_call_ts = 0.0

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
        tgt_lang = _norm_lang(tgt_lang)

        order = self.cfg.get("googleweb_order") or ["googletrans", "deep"]
        last_err = None

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

        raise RuntimeError(f"googleweb translate failed: {last_err}")

    def _translate_deep(self, text, src_lang, tgt_lang):
        from deep_translator import GoogleTranslator

        # deep-translator expects 'auto' or normalized codes like zh-CN
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