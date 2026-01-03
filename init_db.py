#!/usr/bin/env python3
"""
Initialize the himotoki database.
Downloads/loads JMDict and generates conjugations.
"""

import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add the project directory to path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from himotoki.loading.jmdict import load_jmdict

def main():
    data_dir = project_dir / "data"
    db_path = data_dir / "himotoki.db"
    jmdict_path = data_dir / "JMdict_e.xml"
    
    print(f"Database will be created at: {db_path}")
    print(f"JMdict path: {jmdict_path}")
    
    if not jmdict_path.exists():
        print(f"ERROR: JMdict file not found at {jmdict_path}")
        print("Download from: http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz")
        return 1
    
    # Delete existing database if present
    if db_path.exists():
        print(f"Removing existing database: {db_path}")
        db_path.unlink()
    
    try:
        # Load JMDict (this also initializes DB and generates conjugations)
        print("\nLoading JMDict and generating conjugations...")
        print("(This may take 10-20 minutes depending on your system)")
        
        def progress(count):
            print(f"  {count} entries loaded...")
        
        total = load_jmdict(
            xml_path=str(jmdict_path),
            db_path=str(db_path),
            load_extras=True,  # Load conjugations too
            progress_callback=progress
        )
        
        print(f"\n✅ Database initialized at: {db_path}")
        print(f"   Total entries: {total}")
        print("\nYou can now use himotoki:")
        print('  himotoki "日本語テキスト"')
        print('  himotoki -i "学校で勉強しています"')
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
