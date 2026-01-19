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


def load_madlad400_config():
    return {
        "madlad400_model": _env("MADLAD400_MODEL", "google/madlad400-3b-mt"),
        "madlad400_device": _env("MADLAD400_DEVICE", "cpu"),
        "madlad400_torch_threads": _env_int("MADLAD400_TORCH_THREADS", 1),
        "madlad400_batch_size": _env_int("MADLAD400_BATCH_SIZE", 1),
        "madlad400_max_input_tokens": _env_int("MADLAD400_MAX_INPUT_TOKENS", 512),
        "madlad400_max_new_tokens": _env_int("MADLAD400_MAX_NEW_TOKENS", 256),
        "madlad400_num_beams": _env_int("MADLAD400_NUM_BEAMS", 1),
        "madlad400_max_concurrency": _env_int("MADLAD400_MAX_CONCURRENCY", 1),
    }