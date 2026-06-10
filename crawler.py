"""CLI entry point.

Usage: python crawler.py --urls https://example.com --max-pages 100 --output results.json
"""

import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
