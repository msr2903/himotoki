"""
Settings and configuration for Himotoki.

Mirrors settings.lisp from the original Ichiran.
"""

import os
from pathlib import Path

# Data directory paths
PACKAGE_DIR = Path(__file__).parent
DATA_DIR = PACKAGE_DIR / "data"

# Database path - defaults to data/himotoki.db
DEFAULT_DB_PATH = DATA_DIR / "himotoki.db"

# Environment variable for custom database path
DB_PATH = Path(os.environ.get("HIMOTOKI_DB_PATH", DEFAULT_DB_PATH))

# External dictionary paths (user must download these)
JMDICT_PATH = Path(os.environ.get("JMDICT_PATH", DATA_DIR / "JMdict_e.xml"))
KANJIDIC_PATH = Path(os.environ.get("KANJIDIC_PATH", DATA_DIR / "kanjidic2.xml"))

# Conjugation data files (bundled with package)
ROMAJI_MAP_PATH = DATA_DIR / "romaji-map.csv"
CONJUGATION_CSV_PATH = DATA_DIR / "conjugations.csv"

# Source data for custom entries
SOURCES_DIR = DATA_DIR / "sources"

# Download URLs for external dictionaries
JMDICT_URL = "http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz"
KANJIDIC_URL = "http://www.edrdg.org/kanjidic/kanjidic2.xml.gz"

# Debug mode
DEBUG = os.environ.get("HIMOTOKI_DEBUG", "").lower() in ("1", "true", "yes")

# Maximum word length to search
MAX_WORD_LENGTH = 50

# Score cutoff for filtering bad matches
SCORE_CUTOFF = 5

# Gap penalty for segmentation
GAP_PENALTY = -500

# Segment score cutoff ratio
SEGMENT_SCORE_CUTOFF = 2/3


def ensure_data_dirs():
    """Create necessary data directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
