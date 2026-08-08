"""Автовыбор устройства для ML-моделей.

На CUDA включаем fp16 (быстрее и вдвое экономнее по памяти), на CPU — нет:
там fp16 эмулируется и только замедляет работу.
"""

import logging
from functools import lru_cache

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            log.info("ML-модели работают на GPU: %s", name)
            return "cuda"
    except Exception:
        pass
    log.info("ML-модели работают на CPU (GPU недоступен)")
    return "cpu"


def use_fp16() -> bool:
    return get_device() == "cuda"
