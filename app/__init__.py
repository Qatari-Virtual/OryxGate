"""OryxGate application package."""

__version__ = "0.1.0"

# Compatibility shim: Starlette 1.x removed on_startup/on_shutdown from Router.__init__,
# which causes FastAPI versions that still forward those kwargs or access router.on_startup
# to fail on APIRouter initialization or include_router.
try:
    import inspect
    from typing import Any

    import starlette.routing

    _sig = inspect.signature(starlette.routing.Router.__init__)
    if "on_startup" not in _sig.parameters:
        _orig_router_init = starlette.routing.Router.__init__

        def _patched_router_init(
            self: Any, *args: Any, on_startup: Any = None, on_shutdown: Any = None, **kwargs: Any
        ) -> Any:
            self.on_startup = list(on_startup or [])
            self.on_shutdown = list(on_shutdown or [])
            return _orig_router_init(self, *args, **kwargs)

        starlette.routing.Router.__init__ = _patched_router_init  # type: ignore[method-assign]

    import fastapi

    if not hasattr(fastapi.FastAPI, "max_body_size"):
        fastapi.FastAPI.max_body_size = None
except Exception:
    pass
