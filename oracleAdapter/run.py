"""Thin entry wrapper; all research logic/configuration lives in src/oracle."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from oracle.entrypoints import main

if __name__ == "__main__":
    main()
