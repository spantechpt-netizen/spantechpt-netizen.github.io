"""Make the title-block template from a sheet of the office (or the client's) package.

usage: python3 tb_template.py sheet.dxf BLOCK titleblock.dxf ["text to strip" ...]
  sheet.dxf   a converted sheet that carries the title block as a block (e.g. LAY inserted in paper space)
  BLOCK       the title-block block name (survey / probe: the INSERT in the paper layout)
  strip       the texts of that sheet that change from sheet to sheet (drawing title, reference, scale, size,
              area / venue / rev codes, date ...): removed from the template, written per sheet by gen.Sheet
              from project.json -> title_block -> fields.
The template keeps everything else of the block: frame, logos (IMAGE paths as in the source), key plan, general
notes, revision table, names, the code row headers.
"""
import sys
import ezdxf
from ezdxf import recover, xref

src_f, name, out = sys.argv[1:4]
strip = [s.strip() for s in sys.argv[4:]]
src, _ = recover.readfile(src_f)
t = ezdxf.new('R2018', setup=True)
ld = xref.Loader(src, t)
ld.load_block_layout(src.blocks.get(name))
ld.execute()
blk = t.blocks.get(name)
gone = []
for e in list(blk):
    if e.dxftype() in ('TEXT', 'MTEXT'):
        s = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).strip()
        if any(s == k or (len(k) > 6 and s.startswith(k)) for k in strip):
            gone.append(s[:40]); blk.delete_entity(e)
t.modelspace().add_blockref(name, (0, 0))
t.saveas(out)
print('template', out, 'block', name, len(blk), 'entities; stripped', gone)
