import logging


def setup_logging(level="info"):
    level = (level or "info").lower()
    lvl = logging.INFO
    if level == "debug":
        lvl = logging.DEBUG
    elif level == "warning":
        lvl = logging.WARNING
    elif level == "error":
        lvl = logging.ERROR

    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )