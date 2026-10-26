"""DWG -> DXF. ODA File Converter (free, Windows / Linux) or LibreDWG dwg2dxf; a DXF is taken as it is.
If no converter is set the engineer saves the drawing as DXF from AutoCAD (any version)."""
import shutil, subprocess, tempfile
from pathlib import Path

from .paths import settings


class ConvertError(RuntimeError):
    pass


def to_dxf(src, work_dir, log=print):
    src, work_dir = Path(src), Path(work_dir)
    dst = work_dir / (src.stem + '.dxf')
    if src.suffix.lower() == '.dxf':
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        log(f'DXF taken as received: {dst.name}')
        return dst
    if src.suffix.lower() != '.dwg':
        raise ConvertError(f'not a drawing: {src.name}')
    s = settings()
    oda = s.get('oda_converter') or shutil.which('ODAFileConverter')
    if oda and Path(oda).exists():
        with tempfile.TemporaryDirectory() as ind, tempfile.TemporaryDirectory() as outd:
            shutil.copy2(src, Path(ind) / src.name)
            log(f'ODA File Converter: {src.name}')
            subprocess.run([oda, ind, outd, 'ACAD2018', 'DXF', '0', '1', src.name], check=False,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            got = Path(outd) / (src.stem + '.dxf')
            if got.exists():
                shutil.copy2(got, dst); return dst
        log('ODA File Converter produced no DXF')
    d2d = s.get('dwg2dxf') or shutil.which('dwg2dxf')
    if d2d and Path(d2d).exists():
        log(f'LibreDWG dwg2dxf: {src.name}')
        r = subprocess.run([d2d, '-y', '-o', str(dst), str(src)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if dst.exists() and dst.stat().st_size > 0:
            return dst
        log(r.stdout[-2000:])
    raise ConvertError('no DWG converter worked: set ODA File Converter in Settings, or save the drawing as DXF '
                       'from AutoCAD and add the DXF')
