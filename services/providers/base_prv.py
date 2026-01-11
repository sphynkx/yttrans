from services.providers.dummy_prv import DummyProvider
from services.providers.google_prv import GoogleProvider
from services.providers.deepl_prv import DeepLProvider
from services.providers.aws_prv import AwsProvider
from services.providers.hf_marian_prv import HfMarianProvider
from services.providers.googleweb_prv import GoogleWebProvider


def build_provider(cfg):
    engine = (cfg.get("engine") or "dummy").lower()

    if engine == "googleweb":
        return GoogleWebProvider(cfg)

    if engine == "google":
        return GoogleProvider(cfg)
    if engine == "deepl":
        return DeepLProvider(cfg)
    if engine == "aws":
        return AwsProvider(cfg)
    if engine == "hf_marian":
        return HfMarianProvider(cfg)

    if engine == "dummy":
        return DummyProvider(cfg)

    raise RuntimeError(f"Unknown translation engine: {engine}")