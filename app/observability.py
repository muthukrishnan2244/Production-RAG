"""Privacy-first Rius tracing. No telemetry is sent without RIUS_API_KEY."""
import os
import logging
from functools import wraps

log = logging.getLogger(__name__)

def initialize():
    """Call once, before instrumented app modules are loaded."""
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv("RIUS_API_KEY") or os.getenv("RIUS_DISABLED", "false").lower() in ("1", "true", "yes"):
        log.info("Rius observability disabled (no key or kill switch)")
        return
    try:
        import rius
        rius.init(service_name=os.getenv("RIUS_SERVICE_NAME", "atlas-ai-fde"), capture_content=False)
        log.info("Rius observability enabled")
    except Exception:
        log.exception("Rius initialization failed; application will continue without telemetry")

def trace(name):
    """Decorate sync/async functions; never export arguments or return values."""
    def decorate(fn):
        try:
            import rius
            return rius.observe(name=name, capture_input=False, capture_output=False)(fn)
        except ImportError:
            return fn
    return decorate