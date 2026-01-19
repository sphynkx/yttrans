import os
import socket


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

    # Bind addr (server listen address). Only BIND_* controls this.
    bind_host = _env("YTTRANS_BIND_HOST", "0.0.0.0")
    bind_port = _env_int("YTTRANS_BIND_PORT", 9095)

    # Public/advertise addr (what clients should connect to).
    # These names are now reserved for PUBLIC endpoint only.
    public_host = _env("YTTRANS_HOST", "").strip()
    public_port = _env_int("YTTRANS_PORT", bind_port)

    # If public host not set, do NOT guess docker-internal IPs (172.*).
    # Better to return nothing than return a wrong address.
    if public_host in ("0.0.0.0", "127.0.0.1", "localhost"):
        public_host = ""

    # IMPORTANT: default instance_id should match other services (often hostname)
    instance_id = _env("INSTANCE_ID", hostname)

    engine = _env("YTTRANS_ENGINE", "dummy")
    langs = _env_list("YTTRANS_LANGS", "")

    timeout_sec = _env_int("YTTRANS_TIMEOUT_SEC", 60)
    max_parallel = _env_int("YTTRANS_MAX_PARALLEL", 2)
    redis_url = _env("YTTRANS_QUEUE_REDIS_URL", "redis://localhost:6379/0")

    max_total_chars = _env_int("YTTRANS_MAXTOTALCHARS", 4500)

    auth_token = _env("AUTH_TOKEN", "")
    log_level = _env("LOG_LEVEL", "info")

    build_hash = _env("BUILD_HASH", "dev")
    build_time = _env("BUILD_TIME", "")

    job_lang_parallelism = _env_int("JOB_LANG_PARALLELISM", 1)

    return {
        "app_name": "YurTube Caption Translate Service",
        "instance_id": instance_id,
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
        # bind/listen
        "bind_host": bind_host,
        "bind_port": bind_port,
        "bind_addr": f"{bind_host}:{bind_port}",
        # public/advertise
        "advertise_host": public_host,
        "advertise_port": public_port,
    }