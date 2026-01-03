"""
Main entry point for running himotoki as a module.

Usage:
    python -m himotoki "日本語テキスト"
"""

import sys
from himotoki.cli import main

if __name__ == '__main__':
    sys.exit(main())
