import uuid

from utils.json_ut import dumps, loads
from utils.time_ut import now_iso_utc


QUEUE_KEY = "yttrans:jobs:queue"


def job_key(job_id):
    return f"yttrans:job:{job_id}"


def result_key(job_id):
    return f"yttrans:result:{job_id}"


def partial_key(job_id):
    return f"yttrans:partial:{job_id}"


def create_job(r, video_id, engine, target_langs, src_lang):
    job_id = str(uuid.uuid4())

    r.hset(
        job_key(job_id),
        mapping={
            "state": "QUEUED",
            "percent": "0",
            "message": "queued",
            "video_id": video_id,
            "engine": engine,
            "src_lang": src_lang or "auto",
            "target_langs": dumps(target_langs or []),
            "created_at": now_iso_utc(),
            "updated_at": now_iso_utc(),
            "err": "",
            "meta": dumps({}),
        },
    )
    r.lpush(QUEUE_KEY, job_id)
    return job_id


def set_status(r, job_id, state=None, percent=None, message=None, err=None, meta=None):
    m = {"updated_at": now_iso_utc()}
    if state is not None:
        m["state"] = state
    if percent is not None:
        m["percent"] = str(int(percent))
    if message is not None:
        m["message"] = message
    if err is not None:
        m["err"] = err
    if meta is not None:
        m["meta"] = dumps(meta)
    r.hset(job_key(job_id), mapping=m)


def get_status(r, job_id):
    h = r.hgetall(job_key(job_id))
    if not h:
        return None
    target_langs = []
    try:
        target_langs = loads(h.get("target_langs") or "[]")
    except Exception:
        target_langs = []

    meta = {}
    try:
        meta = loads(h.get("meta") or "{}")
    except Exception:
        meta = {}

    return {
        "job_id": job_id,
        "video_id": h.get("video_id", ""),
        "state": h.get("state", "STATE_UNSPECIFIED"),
        "percent": int(h.get("percent") or 0),
        "message": h.get("message") or "",
        "engine": h.get("engine") or "",
        "src_lang": h.get("src_lang") or "auto",
        "target_langs": target_langs,
        "err": h.get("err") or "",
        "meta": meta,
        "created_at": h.get("created_at") or "",
        "updated_at": h.get("updated_at") or "",
    }


def store_result(r, job_id, result_obj, ttl_sec=3600):
    r.set(result_key(job_id), dumps(result_obj), ex=int(ttl_sec))


def load_result(r, job_id):
    s = r.get(result_key(job_id))
    if not s:
        return None
    return loads(s)


def delete_result(r, job_id):
    r.delete(result_key(job_id))


def store_partial_result(r, job_id, partial_obj, ttl_sec=3600):
    r.set(partial_key(job_id), dumps(partial_obj), ex=int(ttl_sec))


def load_partial_result(r, job_id):
    s = r.get(partial_key(job_id))
    if not s:
        return None
    return loads(s)


def delete_partial_result(r, job_id):
    r.delete(partial_key(job_id))