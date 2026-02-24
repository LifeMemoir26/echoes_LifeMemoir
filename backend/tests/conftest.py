from __future__ import annotations

import sys
from pathlib import Path

# Ensure `import src...` works no matter where pytest is launched from.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
