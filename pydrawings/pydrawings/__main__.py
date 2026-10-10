"""`python -m pydrawings --input <file> --out <dir> [options]` - see cli.py."""
import sys

from .cli import main

sys.exit(main())
