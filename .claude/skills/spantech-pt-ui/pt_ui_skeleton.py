"""
Span Tech PT design program - UI skeleton (reference layout)
Ribbon (pyqtribbon) + dockable panels (QtAds) + 2D plan (pyqtgraph) + 3D viewport (pyvistaqt)
+ Fluent theme (qfluentwidgets). UI only: no engineering calculations live here.

Run:  pip install -r requirements-ui.txt && python pt_ui_skeleton.py
"""
import sys

import numpy as np
import pyqtgraph as pg
import pyvista as pv
import PySide6QtAds as QtAds
from PySide6 import QtCore, QtGui, QtWidgets
from pyqtribbon import RibbonBar
from pyvistaqt import QtInteractor
from qfluentwidgets import FluentIcon, setTheme, Theme

RTL = True  # Arabic layout


def tr(ar, en):
    return ar if RTL else en


# ---------------------------------------------------------------- 2D plan canvas
class PlanCanvas(pg.PlotWidget):
    """Plan view: slab outline, columns, tendons. Zoom = wheel, pan = middle/left drag."""

    def __init__(self):
        super().__init__()
        self.setAspectLocked(True)
        self.showGrid(x=True, y=True, alpha=0.15)
        self.setBackground("#1e1e1e" if True else "w")
        self._demo()

    def _demo(self):
        # slab outline
        x = [0, 24, 24, 0, 0]
        y = [0, 0, 16, 16, 0]
        self.plot(x, y, pen=pg.mkPen("#c8c8c8", width=2))
        # columns on an 8 m grid
        cols = [(cx, cy) for cx in (0, 8, 16, 24) for cy in (0, 8, 16)]
        for cx, cy in cols:
            r = QtWidgets.QGraphicsRectItem(cx - 0.3, cy - 0.3, 0.6, 0.6)
            r.setBrush(pg.mkBrush("#9e9e9e"))
            r.setPen(pg.mkPen(None))
            self.addItem(r)
        # banded tendons (X) and distributed (Y) in office-style colours
        for cy in (0, 8, 16):
            self.plot([0.5, 23.5], [cy, cy], pen=pg.mkPen("#ff5252", width=3))
        for cx in np.arange(1, 24, 1.5):
            self.plot([cx, cx], [0.5, 15.5], pen=pg.mkPen("#40c4ff", width=1.5))


# ---------------------------------------------------------------- 3D viewport
class Viewport3D(QtWidgets.QWidget):
    """Stacked floors with a demo moment-contour field on the top slab."""

    def __init__(self):
        super().__init__()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        lay.addWidget(self.plotter)
        self._demo()

    def _demo(self):
        p = self.plotter
        p.set_background("#1e1e1e")
        for lvl in range(3):
            z = lvl * 3.3
            slab = pv.Plane(center=(12, 8, z), direction=(0, 0, 1), i_size=24, j_size=16,
                            i_resolution=48, j_resolution=32)
            if lvl == 2:  # demo contour on the roof
                pts = slab.points
                slab["Mx (kN.m/m)"] = -40 * np.cos(np.pi * pts[:, 0] / 8) * np.cos(np.pi * pts[:, 1] / 8)
                p.add_mesh(slab, scalars="Mx (kN.m/m)", cmap="jet", show_edges=False,
                           scalar_bar_args={"title": "Mx"})
            else:
                p.add_mesh(slab, color="#8d8d8d", opacity=0.9)
            for cx in (0, 8, 16, 24):
                for cy in (0, 8, 16):
                    col = pv.Cube(center=(cx, cy, z - 1.5), x_length=0.6, y_length=0.6, z_length=3.0)
                    p.add_mesh(col, color="#bdbdbd")
        p.add_axes()
        p.view_isometric()


# ---------------------------------------------------------------- main window
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("سبان تك - تصميم البوست تنشن", "Span Tech - PT Design"))
        self.resize(1500, 900)

        central = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        self.setCentralWidget(central)

        self.ribbon = RibbonBar()
        vbox.addWidget(self.ribbon)
        self._build_ribbon()

        self.dock_mgr = QtAds.CDockManager(central)
        vbox.addWidget(self.dock_mgr)
        self._build_docks()

        self.statusBar().showMessage(tr("الوحدات: m, kN   |   المستوى: Level 2   |   Snap: ON",
                                        "Units: m, kN  |  Level 2  |  Snap: ON"))

    # ribbon tabs = the program's workflow
    def _build_ribbon(self):
        tabs = [
            (tr("ملف", "File"), [(tr("جديد", "New"), FluentIcon.ADD), (tr("فتح", "Open"), FluentIcon.FOLDER),
                                 (tr("حفظ", "Save"), FluentIcon.SAVE), (tr("استيراد DXF", "Import DXF"), FluentIcon.DOCUMENT)]),
            (tr("النمذجة", "Model"), [(tr("بلاطة", "Slab"), FluentIcon.LAYOUT), (tr("عمود", "Column"), FluentIcon.UP),
                                     (tr("حائط", "Wall"), FluentIcon.ALIGNMENT), (tr("كمرة", "Beam"), FluentIcon.REMOVE),
                                     (tr("فتحة", "Opening"), FluentIcon.CANCEL), (tr("Drop", "Drop"), FluentIcon.DOWN)]),
            (tr("الكابلات", "Tendons"), [(tr("توليد", "Generate"), FluentIcon.SYNC), (tr("Banded", "Banded"), FluentIcon.MENU),
                                        (tr("Profile", "Profile"), FluentIcon.MARKET), (tr("الأناكر", "Anchors"), FluentIcon.PIN)]),
            (tr("الشرائح", "Strips"), [(tr("Column strip", "Column strip"), FluentIcon.VIEW), (tr("Middle strip", "Middle strip"), FluentIcon.VIEW),
                                      (tr("تحرير", "Edit"), FluentIcon.EDIT)]),
            (tr("التحليل", "Analysis"), [(tr("Mesh", "Mesh"), FluentIcon.TILES), (tr("تشغيل", "Run"), FluentIcon.PLAY),
                                        (tr("Load take-down", "Load take-down"), FluentIcon.DOWNLOAD)]),
            (tr("النتائج", "Results"), [(tr("عزوم", "Moments"), FluentIcon.PIE_SINGLE), (tr("ترخيم", "Deflection"), FluentIcon.SCROLL),
                                       (tr("إجهادات", "Stresses"), FluentIcon.SPEED_HIGH)]),
            (tr("اللوحات", "Drawings"), [(tr("Shop drawings", "Shop drawings"), FluentIcon.PRINT), (tr("BOQ", "BOQ"), FluentIcon.CALENDAR),
                                        (tr("تصدير DXF", "Export DXF"), FluentIcon.SHARE)]),
        ]
        for title, buttons in tabs:
            cat = self.ribbon.addCategory(title)
            panel = cat.addPanel(title)
            for text, icon in buttons:
                panel.addLargeButton(text, icon.icon())

    # four docks around a tabbed document area
    def _build_docks(self):
        # center documents
        plan_dock = QtAds.CDockWidget(tr("مسقط - Level 2", "Plan - Level 2"))
        plan_dock.setWidget(PlanCanvas())
        center = self.dock_mgr.setCentralWidget(plan_dock)

        view_dock = QtAds.CDockWidget(tr("3D", "3D"))
        view_dock.setWidget(Viewport3D())
        self.dock_mgr.addDockWidget(QtAds.RightDockWidgetArea, view_dock, center)

        # project browser (left)
        tree = QtWidgets.QTreeWidget()
        tree.setHeaderHidden(True)
        root = QtWidgets.QTreeWidgetItem(tree, [tr("المشروع", "Project")])
        for lvl in ("Level 1", "Level 2", "Roof"):
            li = QtWidgets.QTreeWidgetItem(root, [lvl])
            for kind in (tr("بلاطات", "Slabs"), tr("أعمدة", "Columns"), tr("حوائط", "Walls"),
                         tr("كمرات", "Beams"), tr("كابلات", "Tendons"), tr("شرائح", "Strips")):
                QtWidgets.QTreeWidgetItem(li, [kind])
        tree.expandAll()
        d = QtAds.CDockWidget(tr("متصفح المشروع", "Project browser"))
        d.setWidget(tree)
        self.dock_mgr.addDockWidget(QtAds.LeftDockWidgetArea, d)

        # properties (right)
        form = QtWidgets.QTableWidget(6, 2)
        form.setHorizontalHeaderLabels([tr("الخاصية", "Property"), tr("القيمة", "Value")])
        rows = [("Element", "Tendon T-14"), ("Strands", "4 x 12.7"), ("Jacking", "75% = 139 kN"),
                ("Profile mark", "A.01"), ("Bonded", "Yes"), ("Duct", "Flat 20x70")]
        for i, (k, v) in enumerate(rows):
            form.setItem(i, 0, QtWidgets.QTableWidgetItem(k))
            form.setItem(i, 1, QtWidgets.QTableWidgetItem(v))
        form.horizontalHeader().setStretchLastSection(True)
        d = QtAds.CDockWidget(tr("الخصائص", "Properties"))
        d.setWidget(form)
        self.dock_mgr.addDockWidget(QtAds.RightDockWidgetArea, d)

        # results / log (bottom)
        tabs = QtWidgets.QTabWidget()
        log = QtWidgets.QPlainTextEdit(readOnly=True)
        log.appendPlainText(tr("جاهز.", "Ready."))
        tabs.addTab(log, tr("السجل", "Log"))
        tabs.addTab(QtWidgets.QTableWidget(0, 6), tr("جدول الكابلات", "Tendon schedule"))
        tabs.addTab(QtWidgets.QTableWidget(0, 5), tr("فحوصات", "Checks"))
        d = QtAds.CDockWidget(tr("النتائج", "Results"))
        d.setWidget(tabs)
        self.dock_mgr.addDockWidget(QtAds.BottomDockWidgetArea, d)


def main():
    app = QtWidgets.QApplication(sys.argv)
    setTheme(Theme.DARK)
    if RTL:
        app.setLayoutDirection(QtCore.Qt.RightToLeft)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
