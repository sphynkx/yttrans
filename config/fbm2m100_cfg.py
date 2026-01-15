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


def load_fbm2m100_config():
    """
    Local transformers-based M2M100 provider.

    Env:
      FBM2M100_MODEL              (default: facebook/m2m100_418M)
      FBM2M100_DEVICE             (default: cpu)
      FBM2M100_TORCH_THREADS      (default: 0 => do not set)
      FBM2M100_MAX_NEW_TOKENS     (default: 256)
      FBM2M100_NUM_BEAMS          (default: 1)
    """
    return {
        "fbm2m100_model": _env("FBM2M100_MODEL", "facebook/m2m100_418M"),
        "fbm2m100_device": _env("FBM2M100_DEVICE", "cpu"),
        "fbm2m100_torch_threads": _env_int("FBM2M100_TORCH_THREADS", 0),
        "fbm2m100_max_input_tokens": _env_int("FBM2M100_MAX_INPUT_TOKENS", 1024),
        "fbm2m100_max_new_tokens": _env_int("FBM2M100_MAX_NEW_TOKENS", 256),
        "fbm2m100_num_beams": _env_int("FBM2M100_NUM_BEAMS", 1),
        "fbm2m100_warmup": _env_int("FBM2M100_WARMUP", 0),
        "fbm2m100_batch_size": _env_int("FBM2M100_BATCH_SIZE", 8),
    }