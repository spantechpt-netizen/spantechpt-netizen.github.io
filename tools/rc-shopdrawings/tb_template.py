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
# AutoCAD refuses ATTRIBs with an incomplete embedded MTEXT (converted drawings): every attribute inside the
# template's blocks becomes a plain TEXT at the same place; OLE frames (empty after conversion) are dropped
fixed = 0
for b in t.blocks:
    for e in list(b):
        if e.dxftype() == 'OLE2FRAME':
            b.delete_entity(e); fixed += 1
        elif e.dxftype() == 'INSERT' and len(e.attribs):
            lay = t.blocks.get(e.dxf.name)
            for a in e.attribs:
                tx = b.add_text(a.dxf.text, height=a.dxf.height, rotation=a.dxf.get('rotation', 0),
                                dxfattribs={'layer': a.dxf.layer, 'style': a.dxf.get('style', 'Standard'),
                                            'insert': a.dxf.insert, 'halign': a.dxf.get('halign', 0),
                                            'valign': a.dxf.get('valign', 0), 'align_point': a.dxf.get('align_point', a.dxf.insert),
                                            'width': a.dxf.get('width', 1), 'color': a.dxf.get('color', 256)})
                fixed += 1
            e.delete_all_attribs()
            for ad in [x for x in lay if x.dxftype() == 'ATTDEF']: lay.delete_entity(ad)
        elif e.dxftype() == 'MTEXT' and e.has_columns:   # column data written back as an embedded object: drop it
            e._columns = None; fixed += 1
# keep the template plain for AutoCAD: dimensions / leaders exploded into lines and texts, no extension dictionaries
for b in t.blocks:
    for e in list(b):
        if e.dxftype() in ('DIMENSION', 'LEADER', 'ARC_DIMENSION'):
            try:
                for v in e.virtual_entities():
                    b.add_entity(v.copy() if v.is_virtual is False else v); fixed += 1
            except Exception:
                pass
            b.delete_entity(e)
        elif e.has_extension_dict:
            e.discard_extension_dict()
aud = t.audit()
t.modelspace().add_blockref(name, (0, 0))
t.saveas(out)
print('template', out, 'block', name, len(blk), 'entities; stripped', gone, '; attribs / OLE / columns / dims fixed', fixed, '; audit fixes', len(aud.fixes))
