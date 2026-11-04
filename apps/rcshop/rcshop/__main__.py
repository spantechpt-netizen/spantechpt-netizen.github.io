import sys

from .cli import main

if __name__ == '__main__':
    # double-click on the program (no arguments) opens the window
    sys.exit(main(sys.argv[1:] or ['gui']))
