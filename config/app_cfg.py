import os
import socket
import uuid


def _env(name, default=""):
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v


def _env_int(name, default):
    v = os.getenv(name)
    if v is None or v == "":
        return int(default)
    return int(v)


def _env_list(name, default_csv):
    csv = _env(name, default_csv)
    items = []
    for x in csv.split(","):
        x = x.strip()
        if x:
            items.append(x)
    return items


def load_config():
    hostname = socket.gethostname()

    host = _env("YTTRANS_HOST", "0.0.0.0")
    port = _env_int("YTTRANS_PORT", 9095)

    # IMPORTANT: default instance_id should match other services (often hostname)
    instance_id = _env("INSTANCE_ID", hostname)

    engine = _env("YTTRANS_ENGINE", "dummy")
    langs = _env_list("YTTRANS_LANGS", "")

    timeout_sec = _env_int("YTTRANS_TIMEOUT_SEC", 60)
    max_parallel = _env_int("YTTRANS_MAX_PARALLEL", 2)
    redis_url = _env("YTTRANS_QUEUE_REDIS_URL", "redis://localhost:6379/0")

    # Limits for google-web
    max_total_chars = _env_int("YTTRANS_MAXTOTALCHARS", 4500)

    auth_token = _env("AUTH_TOKEN", "")
    log_level = _env("LOG_LEVEL", "info")

    build_hash = _env("BUILD_HASH", "dev")
    build_time = _env("BUILD_TIME", "")

    job_lang_parallelism = _env_int("JOB_LANG_PARALLELISM", 1)


    return {
        "app_name": "YurTube Caption Translate Service",
        "instance_id": instance_id,
        "host": host,
        "port": port,
        "bind_addr": f"{host}:{port}",
        "hostname": hostname,
        "engine": engine,
        "langs": langs,
        "default_source_lang": "auto",
        "timeout_sec": timeout_sec,
        "max_parallel": max_parallel,
        "job_lang_parallelism": job_lang_parallelism,
        "redis_url": redis_url,
        "max_total_chars": max_total_chars,
        "auth_token": auth_token,
        "log_level": log_level,
        "build_hash": build_hash,
        "build_time": build_time,
        "version": "0.1.0",
    }