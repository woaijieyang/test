from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
for p in [HERE,HERE.parent/"map_memory/tests",HERE.parent/"observation_pose/tests"]:sys.path.insert(0,str(p))
