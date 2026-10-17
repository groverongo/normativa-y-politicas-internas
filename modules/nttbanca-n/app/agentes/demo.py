import time

from app.core.config import get_settings


def simular_trabajo() -> None:
    """Pausa de los stubs (AGENT_STUB_DELAY_MS) para que en la demo se vea avanzar el pipeline."""
    delay_ms = get_settings().agent_stub_delay_ms
    if delay_ms > 0:
        time.sleep(delay_ms / 1000)
