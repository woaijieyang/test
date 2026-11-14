"""Use the same pinned vendor import root as the private memory worker."""
from pathlib import Path
import sys
source=Path(__file__).resolve().parents[5]/'vendor_sources/EvoMemNav'
if not (source/'evomemnav/policy/coarse.py').is_file():
    raise RuntimeError('Run retrieval tests through the protected project runtime')
sys.path.insert(0,str(source))
