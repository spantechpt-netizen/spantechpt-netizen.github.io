@echo off
rem RC Shop - Windows build (one folder: RCShop.exe + engine\). Run from apps\rcshop in a Python 3.11+ venv:
rem   pip install -r requirements.txt nuitka
rem   build_windows.bat
python -m nuitka --standalone --enable-plugin=tk-inter --windows-console-mode=attach ^
  --include-package=rcshop --include-package=ezdxf --include-package=shapely --include-package=matplotlib --include-package=PIL --include-package=numpy ^
  --include-data-dir=..\..\tools\rc-shopdrawings=engine ^
  --output-filename=RCShop.exe --output-dir=build rcshop_main.py
if errorlevel 1 exit /b 1
echo.
echo Built: build\rcshop_main.dist\RCShop.exe  (copy the whole folder)
