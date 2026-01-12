import asyncio
import logging

from jobs.translate_job import (
    QUEUE_KEY,
    get_status,
    set_status,
    store_result,
    store_partial_result,
)
from services.providers.base_prv import build_provider
from utils.time_ut import now_ms, now_iso_utc
from utils.vtt_ut import (
    extract_translatable_lines,
    inject_translated_lines,
    batch_translate_texts,
    translate_vtt,
)


log = logging.getLogger("yttrans.worker_job")


def _compute_job_weight(src_vtt: str, num_langs: int) -> int:
    """
    Simple heuristic: amount of work roughly proportional to text size * number of target languages.
    """
    try:
        return int(len(src_vtt or "")) * int(num_langs or 0)
    except Exception:
        return 0


def _delay_for_job(weight: int, num_langs: int) -> float:
    """
    Anti-ban pacing. Tuneable heuristic.
    """
    delay = 0.25

    # language count threshold
    if num_langs >= 10:
        delay = 1.0
    if num_langs >= 20:
        delay = 1.8

    # weight threshold (chars * langs)
    if weight >= 200_000:
        delay = max(delay, 1.5)
    if weight >= 500_000:
        delay = max(delay, 2.5)

    return delay


def _is_batch_delim_mismatch(err: Exception) -> bool:
    msg = str(err or "")
    return "delimiter split mismatch after translation" in msg


def _publish_partial(
    r,
    job_id,
    video_id,
    state,
    percent,
    message,
    target_langs,
    entries,
    failed_langs,
    fallback_langs,
    errors,
    engine,
    weight,
    ttl_sec=3600,
):
    """
    Publish incremental progress for UI:
      - ready_langs: langs successfully produced (either batch or fallback)
      - total_langs: requested count
      - meta: diagnostics
    """
    try:
        ready_langs = [e.get("lang", "") for e in (entries or []) if (e.get("lang") or "").strip()]
        total_langs = len(target_langs or [])

        meta = {
            "engine": engine,
            "weight": weight,
            "failed_langs": list(failed_langs or []),
            "fallback_langs": list(fallback_langs or []),
            "errors": dict(errors or {}),
        }

        store_partial_result(
            r,
            job_id,
            {
                "job_id": job_id,
                "video_id": video_id,
                "state": state,
                "percent": int(percent or 0),
                "message": message or "",
                "ready_langs": ready_langs,
                "total_langs": int(total_langs),
                "meta": meta,
            },
            ttl_sec=ttl_sec,
        )
    except Exception:
        log.exception("job=%s video_id=%s partial_publish_failed", job_id, video_id)


async def run_workers(cfg, r, inmem_requests, stop_event):
    """
    inmem_requests: dict job_id -> {video_id, src_vtt, src_lang, target_langs, options}
    """
    max_parallel = int(cfg.get("max_parallel") or 1)
    sem = asyncio.Semaphore(max_parallel)
    provider = build_provider(cfg)

    # pull from global config
    max_total_chars = int(cfg.get("max_total_chars") or 4500)

    async def one_job(job_id):
        async with sem:
            req = inmem_requests.get(job_id)
            if not req:
                set_status(
                    r,
                    job_id,
                    state="FAILED",
                    percent=0,
                    message="missing request payload",
                    err="missing_payload",
                )
                return

            video_id = req.get("video_id", "")
            src_vtt = req.get("src_vtt", "")
            src_lang = req.get("src_lang", "auto")
            target_langs = req.get("target_langs") or []
            options = req.get("options") or {}

            started = now_ms()
            engine = cfg.get("engine")

            log.info(
                "job=%s video_id=%s state=RUNNING engine=%s targets=%s",
                job_id,
                video_id,
                engine,
                target_langs,
            )
            set_status(
                r,
                job_id,
                state="RUNNING",
                percent=1,
                message="running",
                meta={"engine": engine, "started_at": now_iso_utc()},
            )

            entries = []
            total = max(1, len(target_langs))
            done = 0

            failed_langs = []
            errors = {}
            fallback_langs = []

            base_lines, idxs, texts = extract_translatable_lines(src_vtt)
            src_has_trailing_nl = src_vtt.endswith("\n")

            weight = _compute_job_weight(src_vtt, len(target_langs))
            delay_sec = _delay_for_job(weight, len(target_langs))

            progressive_result = {
                "video_id": video_id,
                "default_lang": src_lang if src_lang and src_lang != "auto" else "auto",
                "entries": [],
                "meta": {
                    "source_lang": src_lang or "auto",
                    "engine": engine,
                    "options": options,
                    "started_at": now_iso_utc(),
                    "weight": weight,
                    "failed_langs": [],
                    "fallback_langs": [],
                    "errors": {},
                },
            }

            _publish_partial(
                r=r,
                job_id=job_id,
                video_id=video_id,
                state="RUNNING",
                percent=1,
                message="running",
                target_langs=target_langs,
                entries=entries,
                failed_langs=failed_langs,
                fallback_langs=fallback_langs,
                errors=errors,
                engine=engine,
                weight=weight,
            )

            try:
                for lang in target_langs:
                    lang_started = now_ms()
                    log.info(
                        "job=%s video_id=%s lang=%s state=TRANSLATING weight=%s delay_sec=%.2f max_total_chars=%s",
                        job_id,
                        video_id,
                        lang,
                        weight,
                        delay_sec,
                        max_total_chars,
                    )

                    try:
                        def translate_block_sync(block_text):
                            return provider.translate(text=block_text, src_lang=src_lang, tgt_lang=lang)

                        translated_texts = batch_translate_texts(
                            texts,
                            translate_block_sync,
                            max_total_chars=max_total_chars,
                        )

                        vtt_body = inject_translated_lines(base_lines, idxs, translated_texts)
                        vtt_tgt = vtt_body + ("\n" if src_has_trailing_nl else "")

                        entry = {"lang": lang, "vtt": vtt_tgt}
                        entries.append(entry)

                        progressive_result["entries"].append(entry)
                        store_result(r, job_id, progressive_result, ttl_sec=3600)

                        took = now_ms() - lang_started
                        log.info(
                            "job=%s video_id=%s lang=%s state=OK mode=batch duration_ms=%s",
                            job_id,
                            video_id,
                            lang,
                            took,
                        )

                    except Exception as e:
                        if _is_batch_delim_mismatch(e):
                            log.warning(
                                "job=%s video_id=%s lang=%s batch_failed_delim_mismatch -> fallback=line_by_line err=%s",
                                job_id,
                                video_id,
                                lang,
                                str(e),
                            )
                        else:
                            log.warning(
                                "job=%s video_id=%s lang=%s batch_failed -> fallback=line_by_line err=%s",
                                job_id,
                                video_id,
                                lang,
                                str(e),
                            )

                        try:
                            def translate_line_sync(line):
                                return provider.translate(text=line, src_lang=src_lang, tgt_lang=lang)

                            vtt_tgt = translate_vtt(src_vtt, translate_line_sync)
                            entry = {"lang": lang, "vtt": vtt_tgt}
                            entries.append(entry)

                            fallback_langs.append(lang)

                            progressive_result["entries"].append(entry)
                            progressive_result["meta"]["fallback_langs"] = list(fallback_langs)
                            store_result(r, job_id, progressive_result, ttl_sec=3600)

                            took = now_ms() - lang_started
                            log.info(
                                "job=%s video_id=%s lang=%s state=OK mode=line_by_line duration_ms=%s",
                                job_id,
                                video_id,
                                lang,
                                took,
                            )

                        except Exception as e2:
                            took = now_ms() - lang_started
                            err_txt = str(e2)
                            failed_langs.append(lang)
                            errors[lang] = err_txt

                            progressive_result["meta"]["failed_langs"] = list(failed_langs)
                            progressive_result["meta"]["errors"] = dict(errors)
                            progressive_result["meta"]["fallback_langs"] = list(fallback_langs)
                            store_result(r, job_id, progressive_result, ttl_sec=3600)

                            log.warning(
                                "job=%s video_id=%s lang=%s state=FAILED duration_ms=%s err=%s",
                                job_id,
                                video_id,
                                lang,
                                took,
                                err_txt,
                            )

                    done += 1
                    percent = int(1 + (done / total) * 98)
                    msg = f"translated {done}/{total}"
                    if failed_langs:
                        msg += f", failed={len(failed_langs)}"
                    if fallback_langs:
                        msg += f", fallback={len(fallback_langs)}"

                    set_status(
                        r,
                        job_id,
                        percent=percent,
                        message=msg,
                        meta={
                            "engine": engine,
                            "failed_langs": failed_langs,
                            "fallback_langs": fallback_langs,
                            "weight": weight,
                        },
                    )

                    _publish_partial(
                        r=r,
                        job_id=job_id,
                        video_id=video_id,
                        state="RUNNING",
                        percent=percent,
                        message=msg,
                        target_langs=target_langs,
                        entries=entries,
                        failed_langs=failed_langs,
                        fallback_langs=fallback_langs,
                        errors=errors,
                        engine=engine,
                        weight=weight,
                    )

                    await asyncio.sleep(delay_sec)

                duration_ms = now_ms() - started

                result_obj = {
                    "video_id": video_id,
                    "default_lang": src_lang if src_lang and src_lang != "auto" else "auto",
                    "entries": entries,
                    "meta": {
                        "source_lang": src_lang or "auto",
                        "engine": engine,
                        "options": options,
                        "duration_ms": duration_ms,
                        "completed_at": now_iso_utc(),
                        "failed_langs": failed_langs,
                        "fallback_langs": fallback_langs,
                        "errors": errors,
                        "weight": weight,
                    },
                }
                store_result(r, job_id, result_obj, ttl_sec=3600)

                msg = "done"
                if failed_langs:
                    msg = f"done with failures: {len(failed_langs)}/{len(target_langs)}"

                set_status(
                    r,
                    job_id,
                    state="DONE",
                    percent=100,
                    message=msg,
                    meta={
                        "engine": engine,
                        "duration_ms": duration_ms,
                        "failed_langs": failed_langs,
                        "fallback_langs": fallback_langs,
                        "weight": weight,
                    },
                )

                _publish_partial(
                    r=r,
                    job_id=job_id,
                    video_id=video_id,
                    state="DONE",
                    percent=100,
                    message=msg,
                    target_langs=target_langs,
                    entries=entries,
                    failed_langs=failed_langs,
                    fallback_langs=fallback_langs,
                    errors=errors,
                    engine=engine,
                    weight=weight,
                )

                log.info(
                    "job=%s video_id=%s state=DONE duration_ms=%s ok_langs=%s failed_langs=%s fallback_langs=%s",
                    job_id,
                    video_id,
                    duration_ms,
                    len(entries),
                    len(failed_langs),
                    len(fallback_langs),
                )

            except Exception as e:
                log.exception("job=%s video_id=%s state=FAILED err=%s", job_id, video_id, e)
                set_status(
                    r,
                    job_id,
                    state="FAILED",
                    percent=0,
                    message=str(e),
                    err=str(e),
                    meta={"engine": engine},
                )

                _publish_partial(
                    r=r,
                    job_id=job_id,
                    video_id=video_id,
                    state="FAILED",
                    percent=0,
                    message=str(e),
                    target_langs=target_langs,
                    entries=entries,
                    failed_langs=failed_langs,
                    fallback_langs=fallback_langs,
                    errors=errors,
                    engine=engine,
                    weight=weight,
                )

    loop = asyncio.get_running_loop()

    while not stop_event.is_set():

        def brpop():
            return r.brpop(QUEUE_KEY, timeout=1)

        item = await loop.run_in_executor(None, brpop)
        if not item:
            continue

        _q, job_id = item[0], item[1]
        st = get_status(r, job_id)
        if not st:
            continue

        asyncio.create_task(one_job(job_id))

    await asyncio.sleep(0.2)