import logging

import grpc
from google.protobuf.struct_pb2 import Struct

from jobs.translate_job import (
    create_job,
    delete_result,
    get_status,
    load_result,
    load_partial_result,
)
from utils.auth_ut import require_auth_if_configured

from proto import yttrans_pb2, yttrans_pb2_grpc


log = logging.getLogger("yttrans.translator")


def _state_to_proto(s):
    s = (s or "").upper()
    if s == "QUEUED":
        return yttrans_pb2.Status.QUEUED
    if s == "RUNNING":
        return yttrans_pb2.Status.RUNNING
    if s == "DONE":
        return yttrans_pb2.Status.DONE
    if s == "FAILED":
        return yttrans_pb2.Status.FAILED
    return yttrans_pb2.Status.STATE_UNSPECIFIED


def _dict_to_struct(d):
    st = Struct()
    if d:
        st.update(d)
    return st


def _provider_meta(provider, cfg):
    """
    Returns dict with extra meta fields:
      engine, model, device, ...
    Provider may optionally define get_meta() -> dict.
    """
    meta = {"engine": cfg.get("engine")}

    try:
        if provider and hasattr(provider, "get_meta"):
            m = provider.get_meta()
            if isinstance(m, dict):
                # merge (provider can override engine if it wants)
                meta.update({k: v for k, v in m.items() if v is not None and v != ""})
    except Exception as e:
        meta["warning"] = f"provider_get_meta_failed: {e}"

    return meta


class TranslatorService(yttrans_pb2_grpc.TranslatorServicer):
    def __init__(self, cfg, r, inmem_requests, provider):
        self.cfg = cfg
        self.r = r
        self.inmem_requests = inmem_requests
        self.provider = provider

    def ListLanguages(self, request, context):
        require_auth_if_configured(context, self.cfg)

        langs = []
        meta = _provider_meta(self.provider, self.cfg)

        try:
            langs = self.provider.list_languages()
            if not langs:
                langs = self.cfg.get("langs") or []
        except Exception as e:
            langs = self.cfg.get("langs") or []
            meta["warning"] = f"provider_list_languages_failed: {e}"

        resp = yttrans_pb2.ListLanguagesResponse(
            target_langs=langs,
            default_source_lang=self.cfg.get("default_source_lang", "auto"),
            meta=_dict_to_struct(meta),
        )
        return resp

    def SubmitTranslate(self, request, context):
        require_auth_if_configured(context, self.cfg)

        video_id = (request.video_id or "").strip()
        src_vtt = request.src_vtt or ""
        src_lang = (request.src_lang or "auto").strip() or "auto"
        target_langs = list(request.target_langs or [])

        if not video_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "video_id is required")
        if not src_vtt.strip().startswith("WEBVTT"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "src_vtt must start with WEBVTT")
        if not target_langs:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "target_langs is required")

        engine = self.cfg.get("engine")
        job_id = create_job(
            self.r,
            video_id=video_id,
            engine=engine,
            target_langs=target_langs,
            src_lang=src_lang,
        )

        options = {}
        try:
            options = dict(request.options) if request.options else {}
        except Exception:
            options = {}

        self.inmem_requests[job_id] = {
            "video_id": video_id,
            "src_vtt": src_vtt,
            "src_lang": src_lang,
            "target_langs": target_langs,
            "options": options,
        }

        log.info("submit job=%s video_id=%s engine=%s targets=%s", job_id, video_id, engine, target_langs)

        meta = {"queue": "redis", "engine": engine}
        return yttrans_pb2.JobAck(job_id=job_id, accepted=True, message="accepted", meta=_dict_to_struct(meta))

    def GetStatus(self, request, context):
        require_auth_if_configured(context, self.cfg)

        job_id = (request.job_id or "").strip()
        if not job_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_id is required")

        st = get_status(self.r, job_id)
        if not st:
            context.abort(grpc.StatusCode.NOT_FOUND, "job not found")

        meta = dict(st.get("meta") or {})
        meta["engine"] = st.get("engine") or self.cfg.get("engine")

        # add provider info (model/device) for UI
        meta.update(_provider_meta(self.provider, self.cfg))

        if st.get("err"):
            meta["err"] = st["err"]

        return yttrans_pb2.Status(
            job_id=job_id,
            video_id=st.get("video_id", ""),
            state=_state_to_proto(st.get("state")),
            percent=int(st.get("percent") or 0),
            message=st.get("message") or "",
            meta=_dict_to_struct(meta),
        )

    def GetPartialResult(self, request, context):
        """
        New RPC: must work for QUEUED/RUNNING/DONE/FAILED.
        Returns ready_langs accumulated so far (no VTT payload).
        """
        require_auth_if_configured(context, self.cfg)

        job_id = (request.job_id or "").strip()
        if not job_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_id is required")

        st = get_status(self.r, job_id)
        if not st:
            context.abort(grpc.StatusCode.NOT_FOUND, "job not found")

        part = load_partial_result(self.r, job_id) or {}

        ready_langs = part.get("ready_langs") or []
        total_langs = part.get("total_langs")
        if total_langs is None:
            total_langs = len(st.get("target_langs") or [])

        meta = {}
        try:
            meta = dict(part.get("meta") or {})
        except Exception:
            meta = {}

        # Merge engine + provider info + status errors into meta
        meta["engine"] = st.get("engine") or self.cfg.get("engine")
        meta.update(_provider_meta(self.provider, self.cfg))

        if st.get("err"):
            meta["err"] = st.get("err")

        return yttrans_pb2.PartialTranslationsResult(
            job_id=job_id,
            video_id=st.get("video_id", ""),
            state=_state_to_proto(st.get("state")),
            percent=int(st.get("percent") or 0),
            message=st.get("message") or "",
            ready_langs=list(ready_langs),
            total_langs=int(total_langs or 0),
            meta=_dict_to_struct(meta),
        )

    def GetResult(self, request, context):
        require_auth_if_configured(context, self.cfg)

        job_id = (request.job_id or "").strip()
        if not job_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "job_id is required")

        st = get_status(self.r, job_id)
        if not st:
            context.abort(grpc.StatusCode.NOT_FOUND, "job not found")

        if (st.get("state") or "").upper() != "DONE":
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, f"job is not DONE (state={st.get('state')})")

        res = load_result(self.r, job_id)
        if not res:
            context.abort(grpc.StatusCode.NOT_FOUND, "result not found (expired or already fetched)")

        entries = []
        for e in (res.get("entries") or []):
            entries.append(yttrans_pb2.TranslationEntry(lang=e.get("lang", ""), vtt=e.get("vtt", "")))

        meta = res.get("meta") or {}
        meta["engine"] = meta.get("engine") or st.get("engine") or self.cfg.get("engine")

        # add provider info (model/device)
        meta.update(_provider_meta(self.provider, self.cfg))

        reply = yttrans_pb2.TranslationsResult(
            video_id=res.get("video_id", st.get("video_id", "")),
            default_lang=res.get("default_lang", st.get("src_lang", "auto")),
            entries=entries,
            meta=_dict_to_struct(meta),
        )

        delete_result(self.r, job_id)
        return reply