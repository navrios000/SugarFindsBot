"""Configuración centralizada de logging.

Sale por stdout porque es lo que Render captura y muestra en sus logs.
"""

import logging
import sys


def setup_logger(name: str = "sugarfinds") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # evita duplicar handlers si se llama más de una vez

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    return logger
