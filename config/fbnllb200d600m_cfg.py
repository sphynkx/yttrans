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


def load_fbnllb200d600m_config():
    """
    Local transformers-based NLLB-200 distilled 600M provider.

    Env:
      FBNLLB200D600M_MODEL            (default: facebook/nllb-200-distilled-600M)
      FBNLLB200D600M_DEVICE           (default: cpu)
      FBNLLB200D600M_TORCH_THREADS    (default: 0 => do not set)
      FBNLLB200D600M_MAX_INPUT_TOKENS (default: 1024)
      FBNLLB200D600M_MAX_NEW_TOKENS   (default: 256)
      FBNLLB200D600M_NUM_BEAMS        (default: 1)
      FBNLLB200D600M_BATCH_SIZE       (default: 8)
      FBNLLB200D600M_WARMUP           (default: 0/1)
    """
    return {
        "fbnllb200d600m_model": _env("FBNLLB200D600M_MODEL", "facebook/nllb-200-distilled-600M"),
        "fbnllb200d600m_device": _env("FBNLLB200D600M_DEVICE", "cpu"),
        "fbnllb200d600m_torch_threads": _env_int("FBNLLB200D600M_TORCH_THREADS", 0),
        "fbnllb200d600m_max_input_tokens": _env_int("FBNLLB200D600M_MAX_INPUT_TOKENS", 1024),
        "fbnllb200d600m_max_new_tokens": _env_int("FBNLLB200D600M_MAX_NEW_TOKENS", 256),
        "fbnllb200d600m_num_beams": _env_int("FBNLLB200D600M_NUM_BEAMS", 1),
        "fbnllb200d600m_batch_size": _env_int("FBNLLB200D600M_BATCH_SIZE", 8),
        "fbnllb200d600m_warmup": _env_int("FBNLLB200D600M_WARMUP", 0),
        "fbnllb200d600m_max_concurrency": _env_int("FBNLLB200D600M_MAX_CONCURRENCY", 1),
    }
