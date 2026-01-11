import os


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


def load_googleweb_config():
    return {
        "googleweb_order": _env_list("GOOGLEWEB_ORDER", "googletrans,deep"),
        "googleweb_qps": _env_int("GOOGLEWEB_QPS", 2),
        "googleweb_timeout_sec": _env_int("GOOGLEWEB_TIMEOUT_SEC", 10),
    }