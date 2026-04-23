# build.spec
# ==========
# PyInstaller spec file for the UT Austin Permit Splitter.
#
# HOW TO BUILD THE .EXE:
# ----------------------
# 1. Install PyInstaller:
#       pip install pyinstaller
#
# 2. Install all dependencies:
#       pip install pdf2image pillow opencv-python pytesseract reportlab tkinterdnd2
#
# 3. Make sure Tesseract and Poppler are installed on your build machine.
#    Update the paths below to match your installation.
#
# 4. From the permit_app/ directory, run:
#       pyinstaller build.spec
#
# 5. Your .exe will be at:
#       dist/UEEMobileGaragePermits/UEEMobileGaragePermits.exe
#
# 6. Copy the entire dist/UEEMobileGaragePermits/ folder to Box.
#    Staff download the whole folder and run UEEMobileGaragePermits.exe from inside it.
#
# ── UPDATE THESE PATHS TO MATCH YOUR MACHINE ──────────────────────────────────
import os
import sys

TESSERACT_DIR = r"C:\Program Files\Tesseract-OCR"
POPPLER_BIN   = r"C:\Program Files\poppler\poppler-25.12.0\Library\bin"
# ──────────────────────────────────────────────────────────────────────────────

block_cipher = None

# Collect all binary files to bundle (Tesseract + Poppler executables/DLLs)
binaries = []

# Bundle Tesseract executable and its language data
if os.path.exists(TESSERACT_DIR):
    for fname in os.listdir(TESSERACT_DIR):
        fpath = os.path.join(TESSERACT_DIR, fname)
        if os.path.isfile(fpath):
            binaries.append((fpath, "tesseract"))
    tessdata = os.path.join(TESSERACT_DIR, "tessdata")
    if os.path.exists(tessdata):
        binaries.append((tessdata, "tessdata"))

# Bundle Poppler binaries
if os.path.exists(POPPLER_BIN):
    for fname in os.listdir(POPPLER_BIN):
        fpath = os.path.join(POPPLER_BIN, fname)
        if os.path.isfile(fpath):
            binaries.append((fpath, "poppler"))

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=binaries,
    datas=[
        ("assets/icon.ico", "assets"),   # App icon
        ("permit_splitter.py", "."),      # Core pipeline script
    ],
    hiddenimports=[
        "PIL._tkinter_finder",
        "cv2",
        "pytesseract",
        "reportlab",
        "pdf2image",
        "tkinterdnd2",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UEEMobileGaragePermits",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # No terminal window — GUI only
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="UEEMobileGaragePermits",
)
