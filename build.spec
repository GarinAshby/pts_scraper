# build.spec
# ==========
# PyInstaller spec for the UEE Mobile Garage Permits app.
# Produces a Windows .exe folder bundle OR a self-contained macOS .app.
#
# HOW TO BUILD
# ------------
# 1. Install PyInstaller and the Python deps:
#       pip install pyinstaller
#       pip install pdf2image pillow opencv-python pytesseract reportlab tkinterdnd2
#
# 2. Install Tesseract and Poppler on the build machine:
#       macOS:    brew install tesseract poppler python-tk@3.13
#       Windows:  https://github.com/UB-Mannheim/tesseract/wiki
#                 https://github.com/oschwartz10612/poppler-windows/releases
#
# 3. From the project directory, run:
#       pyinstaller build.spec
#
# 4. Output:
#       Windows: dist/UEEMobileGaragePermits/UEEMobileGaragePermits.exe
#       macOS:   dist/UEEMobileGaragePermits.app  (self-contained)
#
# On macOS, Tesseract + Poppler binaries and their dylibs are bundled inside
# the .app, so end users do NOT need Homebrew. The build machine still needs
# Tesseract & Poppler installed (we copy from /opt/homebrew/...).
# ──────────────────────────────────────────────────────────────────────────────
import os
import platform
import shutil
import subprocess
import sys

IS_MACOS   = platform.system() == "Darwin"
IS_WINDOWS = platform.system() == "Windows"
APP_NAME   = "UEEMobileGaragePermits"

# ── macOS: pre-stage native binaries with relocatable @loader_path rpaths ────
NATIVE_STAGE = os.path.abspath(os.path.join("build", "macos_native"))


def _walk_files(src_dir: str, dest_subdir: str) -> list[tuple]:
    """Return [(src_file, rel_dest_dir)] for every file under src_dir."""
    out = []
    for root, _, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        dest = dest_subdir if rel == "." else os.path.join(dest_subdir, rel)
        for f in files:
            out.append((os.path.join(root, f), dest))
    return out


native_binaries: list[tuple] = []
native_datas:    list[tuple] = []

if IS_MACOS:
    BREW_PREFIX = "/opt/homebrew" if os.path.isdir("/opt/homebrew/bin") else "/usr/local"
    bundler = os.path.join("tools", "macos_bundle.py")

    shutil.rmtree(NATIVE_STAGE, ignore_errors=True)
    os.makedirs(NATIVE_STAGE, exist_ok=True)

    print("[build.spec] staging Tesseract + Poppler...")
    subprocess.check_call([
        sys.executable, bundler,
        os.path.join(NATIVE_STAGE, "tesseract"),
        os.path.join(BREW_PREFIX, "bin", "tesseract"),
    ])
    subprocess.check_call([
        sys.executable, bundler,
        os.path.join(NATIVE_STAGE, "poppler"),
        os.path.join(BREW_PREFIX, "bin", "pdftoppm"),
        os.path.join(BREW_PREFIX, "bin", "pdfinfo"),
    ])

    # tessdata: language data and config files
    tessdata_src = os.path.join(BREW_PREFIX, "share", "tessdata")
    if os.path.isdir(tessdata_src):
        shutil.copytree(tessdata_src, os.path.join(NATIVE_STAGE, "tessdata"))
    else:
        raise SystemExit(f"[build.spec] tessdata not found at {tessdata_src}")

    # IMPORTANT: ship as datas, not binaries. PyInstaller's binary pipeline
    # rewrites rpaths and dedupes against cv2/PIL bundled dylibs (e.g. it
    # symlinks libtesseract.5.dylib to cv2's older copy), which breaks our
    # carefully prepared @loader_path setup. datas are copied verbatim.
    native_datas += _walk_files(os.path.join(NATIVE_STAGE, "tesseract"), "tesseract")
    native_datas += _walk_files(os.path.join(NATIVE_STAGE, "poppler"),  "poppler")
    native_datas += _walk_files(os.path.join(NATIVE_STAGE, "tessdata"), "tessdata")

# ── Windows: bundle Tesseract + Poppler from their install dirs (as before) ──
if IS_WINDOWS:
    TESSERACT_DIR = r"C:\Program Files\Tesseract-OCR"
    POPPLER_BIN   = r"C:\Program Files\poppler\poppler-25.12.0\Library\bin"

    if os.path.exists(TESSERACT_DIR):
        for fname in os.listdir(TESSERACT_DIR):
            fpath = os.path.join(TESSERACT_DIR, fname)
            if os.path.isfile(fpath):
                native_binaries.append((fpath, "tesseract"))
        tessdata = os.path.join(TESSERACT_DIR, "tessdata")
        if os.path.exists(tessdata):
            native_binaries.append((tessdata, "tessdata"))
    if os.path.exists(POPPLER_BIN):
        for fname in os.listdir(POPPLER_BIN):
            fpath = os.path.join(POPPLER_BIN, fname)
            if os.path.isfile(fpath):
                native_binaries.append((fpath, "poppler"))

# ── Datas: assets and the standalone pipeline script ─────────────────────────
datas = [
    ("assets/icon.ico", "assets"),
    ("permit_splitter.py", "."),
] + native_datas

icns_path = os.path.join("assets", "icon.icns")
if os.path.exists(icns_path):
    datas.append((icns_path, "assets"))

# ── Choose icon for the executable ───────────────────────────────────────────
if IS_MACOS and os.path.exists(icns_path):
    exe_icon = icns_path
elif IS_WINDOWS:
    exe_icon = "assets/icon.ico"
else:
    exe_icon = None

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=native_binaries,
    datas=datas,
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
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=not IS_MACOS,
    console=False,
    icon=exe_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=not IS_MACOS,
    upx_exclude=[],
    name=APP_NAME,
)

# ── macOS .app bundle ────────────────────────────────────────────────────────
if IS_MACOS:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=exe_icon,
        bundle_identifier="edu.utexas.uee.mobilegaragepermits",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": "UEE Mobile Garage Permits",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.utilities",
        },
    )
