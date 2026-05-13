"""Phase 0.1 compatibility shim. Will be removed in Phase 0.2."""
import sys
from shared.snapshot import dual_db_snapshot as _real
sys.modules[__name__] = _real
