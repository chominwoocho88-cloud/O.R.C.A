"""Phase 0.1 compatibility shim. Will be removed in Phase 0.2."""
import importlib
import sys
if "apps.jackal.scanner" in sys.modules:
    _real = importlib.reload(sys.modules["apps.jackal.scanner"])
else:
    from apps.jackal import scanner as _real
sys.modules[__name__] = _real
