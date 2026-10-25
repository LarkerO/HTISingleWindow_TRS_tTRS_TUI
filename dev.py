"""Local development launcher; normal installs use the ttrs entry point."""

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "src"))
if os.name == "nt" and sys.prefix == sys.base_prefix and (root / ".deps").is_dir():
    sys.path.insert(0, str(root / ".deps"))

from ttrs.__main__ import main

if __name__ == "__main__":
    main()
