"""python -m lcsc_exporter.app → 打开 GUI。"""
import sys

from .gui import main

if __name__ == "__main__":
    sys.exit(main())
