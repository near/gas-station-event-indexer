import logging


def set_logger(name: str, level: int | str) -> logging.Logger:
    logging.basicConfig(level=level)
    logging.getLogger("near_lake_framework").setLevel(logging.INFO)
    return logging.getLogger(name)
