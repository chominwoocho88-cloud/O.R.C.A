"""Phase 0.1 compatibility shim. Will be removed in Phase 0.2."""
import importlib
import sys
if "apps.jackal.hunter" in sys.modules:
    _real = importlib.reload(sys.modules["apps.jackal.hunter"])
else:
    from apps.jackal import hunter as _real
sys.modules[__name__] = _real
