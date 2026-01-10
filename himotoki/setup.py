"""
Himotoki database setup and data management.

Handles:
- First-time database setup with user consent
- JMdict download from official EDRDG source
- Database generation and storage in ~/.himotoki/
"""

import os
import sys
import gzip
import shutil
import logging
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# Data directory configuration
DEFAULT_DATA_DIR_NAME = ".himotoki"
DB_FILENAME = "himotoki.db"
JMDICT_FILENAME = "JMdict_e.xml"
JMDICT_GZ_FILENAME = "JMdict_e.gz"

# Official EDRDG FTP URL for JMdict
JMDICT_URL = "http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz"

# Approximate sizes for disk space check
REQUIRED_SPACE_GB = 3.2
DOWNLOAD_SIZE_MB = 15
DB_SIZE_GB = 3.0


def get_data_dir() -> Path:
    """
    Get the himotoki data directory path.
    
    Priority:
    1. HIMOTOKI_DATA_DIR environment variable
    2. ~/.himotoki/
    
    Returns:
        Path to data directory (may not exist yet).
    """
    env_dir = os.environ.get("HIMOTOKI_DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / DEFAULT_DATA_DIR_NAME


def get_db_path() -> Path:
    """
    Get the path to the himotoki database file.
    
    Priority:
    1. HIMOTOKI_DB or HIMOTOKI_DB_PATH environment variable
    2. {get_data_dir()}/himotoki.db
    
    Returns:
        Path to database file (may not exist yet).
    """
    env_path = os.environ.get("HIMOTOKI_DB") or os.environ.get("HIMOTOKI_DB_PATH")
    if env_path:
        return Path(env_path)
    return get_data_dir() / DB_FILENAME


def is_database_ready() -> bool:
    """
    Check if the database is ready for use.
    
    Returns:
        True if database exists and has reasonable size.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return False
    # Check if it's at least 100MB (empty or corrupted DBs are much smaller)
    size_mb = db_path.stat().st_size / (1024 * 1024)
    return size_mb > 100


def ensure_data_dir() -> Path:
    """
    Ensure the data directory exists.
    
    Returns:
        Path to data directory.
    """
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_free_space_gb(path: Path) -> float:
    """
    Get available disk space in GB.
    
    Args:
        path: Path to check (uses parent if file doesn't exist).
        
    Returns:
        Free space in GB.
    """
    check_path = path if path.exists() else path.parent
    if not check_path.exists():
        check_path = Path.home()
    
    try:
        stat = shutil.disk_usage(check_path)
        return stat.free / (1024 ** 3)
    except Exception:
        return -1  # Unknown


def check_disk_space(required_gb: float = REQUIRED_SPACE_GB) -> tuple[bool, float]:
    """
    Check if sufficient disk space is available.
    
    Args:
        required_gb: Required space in GB.
        
    Returns:
        Tuple of (has_enough_space, available_gb).
    """
    data_dir = get_data_dir()
    available = get_free_space_gb(data_dir)
    if available < 0:
        return True, available  # Can't check, assume ok
    return available >= required_gb, available


def download_file(
    url: str,
    dest: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> bool:
    """
    Download a file from URL with optional progress.
    
    Args:
        url: URL to download.
        dest: Destination path.
        progress_callback: Optional callback(downloaded_bytes, total_bytes).
        
    Returns:
        True if successful.
    """
    try:
        import urllib.request
        import urllib.error
        
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        def reporthook(block_num, block_size, total_size):
            if progress_callback:
                downloaded = block_num * block_size
                progress_callback(downloaded, total_size)
        
        urllib.request.urlretrieve(url, dest, reporthook=reporthook)
        return True
        
    except urllib.error.URLError as e:
        logger.error(f"Download failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False


def download_jmdict(
    dest_dir: Optional[Path] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Optional[Path]:
    """
    Download and extract JMdict from EDRDG.
    
    Args:
        dest_dir: Destination directory (default: data_dir).
        progress_callback: Optional callback for status messages.
        
    Returns:
        Path to extracted XML file, or None on failure.
    """
    if dest_dir is None:
        dest_dir = ensure_data_dir()
    
    gz_path = dest_dir / JMDICT_GZ_FILENAME
    xml_path = dest_dir / JMDICT_FILENAME
    
    # Download gzipped file
    if progress_callback:
        progress_callback(f"Downloading JMdict from {JMDICT_URL}...")
    
    def download_progress(downloaded: int, total: int):
        if total > 0 and progress_callback:
            pct = int(downloaded * 100 / total)
            mb = downloaded / (1024 * 1024)
            progress_callback(f"  Downloading: {mb:.1f}MB ({pct}%)")
    
    if not download_file(JMDICT_URL, gz_path, download_progress):
        return None
    
    # Extract
    if progress_callback:
        progress_callback("Extracting JMdict...")
    
    try:
        with gzip.open(gz_path, 'rb') as f_in:
            with open(xml_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove compressed file
        gz_path.unlink()
        
        if progress_callback:
            size_mb = xml_path.stat().st_size / (1024 * 1024)
            progress_callback(f"  Extracted: {size_mb:.1f}MB")
        
        return xml_path
        
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return None


def get_bundled_data_path(filename: str) -> Optional[Path]:
    """
    Get path to bundled data file (CSVs etc).
    
    Args:
        filename: Name of the data file.
        
    Returns:
        Path to file if found, else None.
    """
    # Check package data directory
    package_data = Path(__file__).parent.parent / "data"
    if (package_data / filename).exists():
        return package_data / filename
    
    # Check user data directory
    user_data = get_data_dir()
    if (user_data / filename).exists():
        return user_data / filename
    
    return None


def copy_bundled_data(dest_dir: Path) -> bool:
    """
    Copy bundled CSV data files to destination.
    
    Args:
        dest_dir: Destination directory.
        
    Returns:
        True if all files copied successfully.
    """
    package_data = Path(__file__).parent.parent / "data"
    csv_files = ["kwpos.csv", "conj.csv", "conjo.csv"]
    
    for filename in csv_files:
        src = package_data / filename
        if src.exists():
            dest = dest_dir / filename
            if not dest.exists():
                shutil.copy2(src, dest)
    
    return True


def run_setup(
    force: bool = False,
    confirm: bool = True,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Run full database setup.
    
    Args:
        force: If True, rebuild even if database exists.
        confirm: If True, prompt for confirmation (ignored if not interactive).
        progress_callback: Optional callback for progress messages.
        
    Returns:
        True if setup completed successfully.
    """
    import time
    
    def log(msg: str):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
    
    # Check if already set up
    if is_database_ready() and not force:
        log(f"✅ Database already exists at: {get_db_path()}")
        return True
    
    # Check disk space
    has_space, available_gb = check_disk_space()
    if not has_space:
        log(f"❌ Insufficient disk space!")
        log(f"   Required: ~{REQUIRED_SPACE_GB}GB")
        log(f"   Available: {available_gb:.1f}GB")
        return False
    
    # Set up data directory
    data_dir = ensure_data_dir()
    db_path = get_db_path()
    
    log(f"📁 Data directory: {data_dir}")
    log("")
    
    # Download JMdict if needed
    jmdict_path = data_dir / JMDICT_FILENAME
    if not jmdict_path.exists():
        log("📥 Step 1/3: Downloading JMdict dictionary...")
        jmdict_path = download_jmdict(data_dir, log)
        if jmdict_path is None:
            log("❌ Failed to download JMdict")
            return False
    else:
        log(f"✓ JMdict already exists: {jmdict_path}")
    
    log("")
    
    # Copy bundled CSVs
    log("📋 Step 2/3: Preparing conjugation data...")
    copy_bundled_data(data_dir)
    log("  ✓ Conjugation data ready")
    log("")
    
    # Generate database
    log("🔨 Step 3/3: Generating database (this takes 10-20 minutes)...")
    
    # Remove existing database
    if db_path.exists():
        db_path.unlink()
    
    try:
        from himotoki.loading.jmdict import load_jmdict
        
        start_time = time.perf_counter()
        last_update = start_time
        
        def loading_progress(count: int):
            nonlocal last_update
            now = time.perf_counter()
            if now - last_update >= 5:  # Update every 5 seconds
                elapsed = now - start_time
                log(f"  {count:,} entries loaded ({elapsed:.0f}s)...")
                last_update = now
        
        # Update HIMOTOKI_DB_PATH for the loading process
        os.environ["HIMOTOKI_DB_PATH"] = str(db_path)
        
        total = load_jmdict(
            xml_path=str(jmdict_path),
            db_path=str(db_path),
            load_extras=True,
            batch_size=5000,
            progress_callback=loading_progress,
        )
        
        elapsed = time.perf_counter() - start_time
        db_size_gb = db_path.stat().st_size / (1024 ** 3)
        
        log("")
        log("━" * 50)
        log("✅ Setup complete!")
        log(f"   Entries: {total:,}")
        log(f"   Time: {elapsed/60:.1f} minutes")
        log(f"   Database: {db_path} ({db_size_gb:.1f}GB)")
        log("━" * 50)
        
        return True
        
    except Exception as e:
        logger.exception("Database generation failed")
        log(f"❌ Database generation failed: {e}")
        return False


def prompt_for_setup() -> bool:
    """
    Display first-use setup prompt and get user confirmation.
    
    Returns:
        True if user confirms, False otherwise.
    """
    has_space, available_gb = check_disk_space()
    space_status = "✓" if has_space else "⚠️  INSUFFICIENT"
    
    print()
    print("━" * 54)
    print("🧶 Welcome to Himotoki!")
    print("━" * 54)
    print()
    print("First-time setup required. This will:")
    print(f"  • Download JMdict dictionary data (~{DOWNLOAD_SIZE_MB}MB compressed)")
    print(f"  • Generate optimized SQLite database (~{DB_SIZE_GB:.0f}GB)")
    print(f"  • Store data in {get_data_dir()}")
    print()
    print(f"⚠️  Disk space required: ~{REQUIRED_SPACE_GB}GB")
    if available_gb > 0:
        print(f"    Available space:     {available_gb:.1f}GB {space_status}")
    print()
    print("Setup takes approximately 10-20 minutes.")
    print()
    
    if not has_space:
        print("❌ Insufficient disk space. Please free up space and try again.")
        return False
    
    # Check if running interactively
    if not sys.stdin.isatty():
        print("Non-interactive mode. Use 'himotoki setup --yes' to proceed.")
        return False
    
    try:
        response = input("Proceed with setup? [Y/n]: ").strip().lower()
        return response in ("", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        print("\nSetup cancelled.")
        return False


def ensure_database_or_prompt() -> bool:
    """
    Ensure database is ready, prompting for setup if needed.
    
    This is the main entry point for first-use experience.
    Called by CLI before any command that needs the database.
    
    Returns:
        True if database is ready, False if setup was declined or failed.
    """
    if is_database_ready():
        return True
    
    # Prompt for setup
    if not prompt_for_setup():
        return False
    
    # Run setup
    print()
    return run_setup(confirm=False)
