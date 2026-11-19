"""Where Omarum keeps things. Stdlib only."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "omarum"
