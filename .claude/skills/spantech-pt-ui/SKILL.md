---
name: spantech-pt-ui
description: UI stack and layout rules for Span Tech's own PT slab design program (the RAM Concept-like program, PT3D / Auto PT Suite successor). Use whenever the user asks to build, change or style any screen, window, panel, ribbon, viewport, plan canvas or table of the PT design program, or says "الواجهة / الشاشة / اللوحة / الريبون / الفيوبورت" about it. Do NOT use Tkinter for this program.
---

# Span Tech PT program - UI stack

The UI of the PT design program is built ONLY with this Qt stack (pip names, pinned in requirements-ui.txt):

| Role | Package | Import |
|---|---|---|
| Base GUI | PySide6 | `from PySide6 import QtWidgets, QtCore, QtGui` |
| Dockable panels (project tree / properties / results) | PySide6-QtAds | `import PySide6QtAds as QtAds` |
| Ribbon (Revit-style tabs) | pyqtribbon | `from pyqtribbon import RibbonBar` |
| Modern look, dark mode, settings cards | PySide6-Fluent-Widgets | `from qfluentwidgets import ...` |
| 3D viewport (floors, contours, picking) | pyvistaqt + pyvista | `from pyvistaqt import QtInteractor` |
| 2D plan / tendons / strips canvas | pyqtgraph | `import pyqtgraph as pg` |
| Tables (tendon schedule, BOQ) | Qt built-in | `QTableView` + model over pandas |

Verified: all install together and import without conflict (Oct 2026).

## Hard rules
1. Never use Tkinter for any new screen of this program. Existing Tkinter screens of Auto PT Suite are ported one by one into the Qt main window.
2. Keep the UI separate from the engine: `ui/` (windows, panels, widgets) never does calculations; it calls `engine/` (DXF reading, tendon generation, RAM/ADAPT I/O, analysis). The engine must stay importable without Qt so a web version can reuse it later.
3. Main window layout (the "RAM + Revit + ADAPT" layout):
   - Top: RibbonBar with tabs: ملف / النمذجة (Model) / الكابلات (Tendons) / الشرائح (Strips) / التحليل (Analysis) / النتائج (Results) / اللوحات (Drawings).
   - Left dock: project browser (levels → slabs, columns, walls, beams, tendons, strips) as a tree.
   - Center: tabbed document area — 2D plan canvas (pyqtgraph) and 3D viewport (pyvistaqt); both can be open side by side.
   - Right dock: properties panel of the selected element (editable; applies live).
   - Bottom dock: results / log / tables (schedules, BOQ, checks).
   - Status bar: units, level, snap, coordinates.
   - Layouts are saved/restored with QtAds `saveState()/restoreState()`.
4. 2D canvas rules: zoom/pan with wheel and middle mouse, snap to grid and to element points, rubber-band selection, elements are selectable items with a context menu; tendons in the office colours per profile group; design strips editable by dragging centre and width (as the user asked for Auto PT Suite).
5. 3D viewport rules: each level is a separate actor set so levels can be shown/hidden; contour plots (moment, deflection, stress) are drawn as scalar fields on the slab mesh with a colour bar; clicking an element selects it in the tree and properties panel.
6. Language: UI strings go through a single `tr()`/dictionary so Arabic (RTL) and English both work; Arabic layout mirrors with `QApplication.setLayoutDirection(Qt.RightToLeft)`.
7. Terminology: PT anchors are always "الأناكر" (singular الأنكر), never المراسي/مرساة.
8. Theme: qfluentwidgets dark/light following system; office accent colour; icons from Fluent icon set.
9. Every build keeps the user's versioning convention (sequential build number + CHANGELOG entry) as in the auto-pt-suite skill.

## Starter
`pt_ui_skeleton.py` in this folder is the reference main window (ribbon + 4 docks + 2D canvas + 3D viewport). Extend it; do not restart from scratch.

Run: `pip install -r requirements-ui.txt` then `python pt_ui_skeleton.py`.
