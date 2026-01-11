import argparse
import os

from dotenv import load_dotenv

from config.app_cfg import load_config
from config.googleweb_cfg import load_googleweb_config
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

    serve(cfg, host=args.host, port=args.port)


if __name__ == "__main__":
    main()