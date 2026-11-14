from pathlib import Path
import sys
# Reuse pure graph fixtures; all simulator API tests stay in this package.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"graphAdapter/tests"))
