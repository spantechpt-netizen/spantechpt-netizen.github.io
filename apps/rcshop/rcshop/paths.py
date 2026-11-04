"""Where the engine and the user settings live (source checkout, or a frozen .exe with the engine beside it)."""
import json, os, sys
from pathlib import Path

FROZEN = bool(getattr(sys, 'frozen', False) or '__compiled__' in globals())
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
USER_DIR = Path(os.environ.get('RCSHOP_HOME', Path.home() / '.rcshop'))
SETTINGS_FILE = USER_DIR / 'settings.json'
PROFILES_DIR = USER_DIR / 'profiles'

DEFAULTS = {
    'engine_dir': '',          # empty: next to the program (frozen) or tools/rc-shopdrawings of the checkout
    'engine_python': '',       # empty: this Python (source run) / the program itself (frozen)
    'oda_converter': '',       # ODAFileConverter.exe (free, opendesign.com) for DWG -> DXF
    'dwg2dxf': '',             # LibreDWG dwg2dxf, the alternative converter
    'max_zip_mb': 30,          # delivery parts (mail / upload limit)
}


def settings():
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    USER_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s, indent=1), encoding='utf-8')


def engine_dir():
    s = settings()
    for cand in (os.environ.get('RCSHOP_ENGINE'), s.get('engine_dir'),
                 APP_DIR / 'engine', APP_DIR.parent.parent / 'tools' / 'rc-shopdrawings'):
        if cand and (Path(cand) / 'gen.py').exists():
            return Path(cand).resolve()
    raise FileNotFoundError('engine not found: set "engine_dir" in the settings (folder holding gen.py)')
