"""Entry point of the built program (RCShop.exe): no arguments opens the window."""
import sys

from rcshop.cli import main

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or ['gui']))
