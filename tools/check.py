"""Run checks with the bundled runtime or a normal virtualenv."""

import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
if os.name == "nt" and sys.prefix == sys.base_prefix and (root / ".deps").is_dir():
    sys.path.insert(0, str(root / ".deps"))

import pytest

raise SystemExit(pytest.main([str(root / "tests"), "-q", *sys.argv[1:]]))
