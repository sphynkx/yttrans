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


def load_mbart50_config():
    return {
        # recommended MT checkpoint
        "mbart50_model": _env("MBART50_MODEL", "facebook/mbart-large-50-many-to-many-mmt"),
        "mbart50_device": _env("MBART50_DEVICE", "cpu"),
        "mbart50_torch_threads": _env_int("MBART50_TORCH_THREADS", 1),
        "mbart50_batch_size": _env_int("MBART50_BATCH_SIZE", 1),
        "mbart50_max_input_tokens": _env_int("MBART50_MAX_INPUT_TOKENS", 512),
        "mbart50_max_new_tokens": _env_int("MBART50_MAX_NEW_TOKENS", 256),
        "mbart50_num_beams": _env_int("MBART50_NUM_BEAMS", 1),
        "mbart50_max_concurrency": _env_int("MBART50_MAX_CONCURRENCY", 1),
    }