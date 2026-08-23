"""Run every tests/test_*.py as a subprocess.

Run: python3 tests/run_all.py
"""

import subprocess
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
failed = 0
ran = 0
for path in sorted(here.glob("test_*.py")):
    ran += 1
    print(f"\n########## {path.name} ##########", flush=True)
    result = subprocess.run([sys.executable, str(path)])
    if result.returncode != 0:
        failed += 1

print(f"\n{ran - failed}/{ran} test files passed")
sys.exit(1 if failed else 0)
