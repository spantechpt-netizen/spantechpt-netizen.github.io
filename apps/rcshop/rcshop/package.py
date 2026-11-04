"""The delivery: work/out (DXF + remarks) in zip parts under the size limit, one folder per package / zone kept."""
import time, zipfile
from pathlib import Path

from .paths import settings


def run(ws, log=print):
    out = ws.work / 'out'
    files = sorted(p for p in out.rglob('*') if p.is_file() and p.suffix.lower() in ('.dxf', '.txt', '.pdf', '.csv'))
    if not files:
        log('nothing to pack'); return 1
    limit = settings().get('max_zip_mb', 30) * 1024 * 1024 * 0.95
    ws.deliveries.mkdir(exist_ok=True)
    stem = f"{ws.name.replace(' ', '_')}_{time.strftime('%Y%m%d_%H%M')}"
    part, size, zf, made = 0, 0, None, []
    for f in files:
        est = f.stat().st_size * 0.25 if f.suffix.lower() == '.dxf' else f.stat().st_size   # DXF zips to ~1/4
        if zf is None or size + est > limit:
            if zf: zf.close()
            part += 1; size = 0
            path = ws.deliveries / f'{stem}_part{part}.zip'
            zf = zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED); made.append(path)
        zf.write(f, f.relative_to(out)); size += est
    zf.close()
    if len(made) == 1:
        single = ws.deliveries / f'{stem}.zip'; made[0].replace(single); made = [single]
    for m in made:
        log(f'{m.name}  {m.stat().st_size / 1e6:.1f} MB')
        if m.stat().st_size > settings().get('max_zip_mb', 30) * 1024 * 1024:
            log(f'  WARNING: {m.name} is over the limit (one file alone is bigger)')
    return 0
