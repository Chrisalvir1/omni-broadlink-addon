import sys
from pathlib import Path

ADDON_SRC = Path(__file__).resolve().parents[1] / "omni-broadlink-addon"
sys.path.insert(0, str(ADDON_SRC))
