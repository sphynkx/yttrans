import asyncio
import logging

from jobs.translate_job import QUEUE_KEY, get_status, set_status, store_result
from services.providers.base_prv import build_provider
from utils.time_ut import now_ms, now_iso_utc
from utils.vtt_ut import extract_translatable_lines, inject_translated_lines, batch_translate_texts


log = logging.getLogger("yttrans.worker_job")


async def run_workers(cfg, r, inmem_requests, stop_event):
    """
    inmem_requests: dict job_id -> {video_id, src_vtt, src_lang, target_langs, options}
    """
    max_parallel = int(cfg.get("max_parallel") or 1)
    sem = asyncio.Semaphore(max_parallel)
    provider = build_provider(cfg)

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

            try:
                base_lines, idxs, texts = extract_translatable_lines(src_vtt)
                src_has_trailing_nl = src_vtt.endswith("\n")

                for lang in target_langs:
                    def translate_block_sync(block_text):
                        return provider.translate(text=block_text, src_lang=src_lang, tgt_lang=lang)

                    translated_texts = batch_translate_texts(
                        texts,
                        translate_block_sync,
                        max_total_chars=8000,
                    )

                    vtt_body = inject_translated_lines(base_lines, idxs, translated_texts)
                    vtt_tgt = vtt_body + ("\n" if src_has_trailing_nl else "")

                    entries.append({"lang": lang, "vtt": vtt_tgt})

                    done += 1
                    percent = int(1 + (done / total) * 98)
                    set_status(
                        r,
                        job_id,
                        percent=percent,
                        message=f"translated {done}/{total}",
                        meta={"engine": engine},
                    )
                    await asyncio.sleep(0)

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
                    },
                }
                store_result(r, job_id, result_obj, ttl_sec=3600)
                set_status(
                    r,
                    job_id,
                    state="DONE",
                    percent=100,
                    message="done",
                    meta={"engine": engine, "duration_ms": duration_ms},
                )
                log.info(
                    "job=%s video_id=%s state=DONE duration_ms=%s",
                    job_id,
                    video_id,
                    duration_ms,
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