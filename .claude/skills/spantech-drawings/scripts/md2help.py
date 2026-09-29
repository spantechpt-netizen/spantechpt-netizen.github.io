"""Regenerate the app help page from the office workflow Markdown (run from the repo root).

usage: python3 md2help.py docs/RAM-DRAWINGS-WORKFLOW.md
Keeps the <head> of the existing public/help/ram-drawings-workflow.html and rewrites its body.
"""
import re, html, sys
md = open(sys.argv[1] if len(sys.argv) > 1 else 'docs/RAM-DRAWINGS-WORKFLOW.md', encoding='utf8').read()
old = open('public/help/ram-drawings-workflow.html', encoding='utf8').read()
head = old[:old.index('<div class="doc">')]
def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r'`([^`]+)`', lambda m: '<code>' + m.group(1) + '</code>', t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)
    return t
out = ['<div class="doc">', '<div class="top"><a href="../#/drawings">← رجوع للبرنامج</a></div>']
lines = md.split('\n'); i = 0
def flush_list(items, ordered):
    return ('<ol>' if ordered else '<ul>') + ''.join('<li>' + x + '</li>' for x in items) + ('</ol>' if ordered else '</ul>')
while i < len(lines):
    ln = lines[i]
    if ln.startswith('```'):
        buf = []; i += 1
        while i < len(lines) and not lines[i].startswith('```'): buf.append(lines[i]); i += 1
        out.append('<pre dir="ltr">' + html.escape('\n'.join(buf)) + '</pre>'); i += 1; continue
    m = re.match(r'^(#{1,3}) (.*)', ln)
    if m:
        out.append('<h%d>%s</h%d>' % (len(m.group(1)), inline(m.group(2)), len(m.group(1)))); i += 1; continue
    if ln.strip() == '---': out.append('<hr>'); i += 1; continue
    if ln.startswith('> '):
        buf = []
        while i < len(lines) and lines[i].startswith('> '): buf.append(lines[i][2:]); i += 1
        out.append('<blockquote>' + inline(' '.join(buf)) + '</blockquote>'); continue
    if ln.startswith('|'):
        rows = []
        while i < len(lines) and lines[i].startswith('|'): rows.append(lines[i]); i += 1
        cells = [[c.strip() for c in r.strip().strip('|').split('|')] for r in rows if not re.match(r'^\|\s*-', r)]
        t = '<table><thead><tr>' + ''.join('<th>' + inline(c) + '</th>' for c in cells[0]) + '</tr></thead><tbody>'
        for r in cells[1:]: t += '<tr>' + ''.join('<td>' + inline(c) + '</td>' for c in r) + '</tr>'
        out.append(t + '</tbody></table>'); continue
    m = re.match(r'^(\s*)(\d+[أ-ي]?\.|[-*])\s+(.*)', ln)
    if m and not ln.startswith('   '):
        ordered = m.group(2)[0].isdigit(); items = []
        while i < len(lines):
            m2 = re.match(r'^(\d+[أ-ي]?\.|[-*])\s+(.*)', lines[i])
            if m2 and (m2.group(1)[0].isdigit()) == ordered:
                items.append(inline(m2.group(2))); i += 1
                while i < len(lines) and lines[i].startswith('   '):
                    items[-1] += ' ' + inline(re.sub(r'^\s+[-*]\s*', '• ', lines[i])); i += 1
            else: break
        out.append(flush_list(items, ordered)); continue
    if ln.strip():
        out.append('<p>' + inline(ln.strip()) + '</p>')
    i += 1
out += ['</div>', '</body>', '</html>', '']
outp = sys.argv[2] if len(sys.argv) > 2 else 'public/help/ram-drawings-workflow.html'
if len(sys.argv) > 3: head = head.replace('<title>خطوات عمل لوحات التسليح من RAM Concept · سبان تك</title>', '<title>' + sys.argv[3] + '</title>')
open(outp, 'w', encoding='utf8').write(head + '\n'.join(out))
print('html ok', len(out))
