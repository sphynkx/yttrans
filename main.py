import argparse
import os

from dotenv import load_dotenv

from config.app_cfg import load_config
from config.googleweb_cfg import load_googleweb_config
from config.fbm2m100_cfg import load_fbm2m100_config
from config.fbnllb200d600m_cfg import load_fbnllb200d600m_config
from config.madlad400_cfg import load_madlad400_config
from services.grpc_srv import serve


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default=os.getenv("YTTRANS_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.getenv("YTTRANS_PORT", "9095")))
    return p.parse_args()


def main():
    load_dotenv()
    args = _parse_args()

    cfg = load_config()

    engine = (cfg.get("engine") or "").lower()
    if engine == "googleweb":
        cfg.update(load_googleweb_config())
    if engine == "fbm2m100":
        cfg.update(load_fbm2m100_config())
    if engine == "fbnllb200d600m":
        cfg.update(load_fbnllb200d600m_config())
    if engine == "madlad400":
        cfg.update(load_madlad400_config())

    serve(cfg, host=args.host, port=args.port)


if __name__ == "__main__":
    main()