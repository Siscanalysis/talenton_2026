"""Make the checkout's own ``src/`` win over any editable install.

Without this, a git worktree would silently test the source tree of the main
checkout, which would defeat the whole point of parallel branch work.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
