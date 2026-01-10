import asyncio
import logging
import time
from concurrent import futures

import grpc
from grpc_reflection.v1alpha import reflection

import contextlib

from jobs.worker_job import run_workers
from services.health_srv import HealthService
from services.info_srv import InfoService
from services.translator_srv import TranslatorService
from services.providers.base_prv import build_provider
from utils.redis_ut import redis_client
from utils.time_ut import now_iso_utc

from grpc_health.v1 import health_pb2_grpc

from proto import info_pb2, info_pb2_grpc
from proto import yttrans_pb2, yttrans_pb2_grpc

log = logging.getLogger("yttrans.grpc")


def serve(cfg, host="0.0.0.0", port=9095):
    from utils.log_ut import setup_logging

    setup_logging(cfg.get("log_level", "info"))

    r = redis_client(cfg["redis_url"])
    provider = build_provider(cfg)
    inmem_requests = {}

    started_at = time.time()
    started_at_iso = now_iso_utc()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    yttrans_pb2_grpc.add_TranslatorServicer_to_server(
        TranslatorService(cfg, r, inmem_requests, provider), server
    )
    info_pb2_grpc.add_InfoServicer_to_server(
        InfoService(cfg, started_at_epoch=started_at, started_at_iso=started_at_iso), server
    )
    health_pb2_grpc.add_HealthServicer_to_server(HealthService(), server)

    service_names = (
        yttrans_pb2.DESCRIPTOR.services_by_name["Translator"].full_name,
        info_pb2.DESCRIPTOR.services_by_name["Info"].full_name,
        "grpc.health.v1.Health",
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    bind = f"{host}:{port}"
    server.add_insecure_port(bind)

    async def _run():
        stop_event = asyncio.Event()
        worker_task = asyncio.create_task(run_workers(cfg, r, inmem_requests, stop_event))

        log.info("starting gRPC server on %s", bind)
        server.start()

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            log.info("stopping workers")
            stop_event.set()
            try:
                await asyncio.wait_for(worker_task, timeout=2.0)
            except asyncio.TimeoutError:
                worker_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker_task

            log.info("stopping gRPC server")
            server.stop(grace=1)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        log.info("shutdown requested (Ctrl+C)")


