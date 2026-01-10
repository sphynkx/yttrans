import os
import time

from utils.auth_ut import require_auth_if_configured

from proto import info_pb2, info_pb2_grpc


class InfoService(info_pb2_grpc.InfoServicer):
    def __init__(self, cfg, started_at_epoch, started_at_iso):
        self.cfg = cfg
        self.started_at_epoch = started_at_epoch
        self.started_at_iso = started_at_iso

    def All(self, request, context):
        require_auth_if_configured(context, self.cfg)

        uptime = int(time.time() - self.started_at_epoch)

        resp = info_pb2.InfoResponse(
            app_name=self.cfg.get("app_name", "yttrans"),
            instance_id=self.cfg.get("instance_id", ""),
            host=self.cfg.get("bind_addr", ""),
            version=self.cfg.get("version", "0.0.0"),
            uptime=uptime,
            build_hash=self.cfg.get("build_hash", ""),
            build_time=self.cfg.get("build_time", ""),
        )

        resp.metrics["uptime_sec"] = float(uptime)
        return resp

    def Languages(self, request, context):
        require_auth_if_configured(context, self.cfg)

        langs = self.cfg.get("langs") or []
        return info_pb2.InfoLanguagesResponse(
            target_langs=langs,
            default_source_lang=self.cfg.get("default_source_lang", "auto"),
        )