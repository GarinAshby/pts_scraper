"""
tools/fixup_macos_app.py
========================
Run AFTER `pyinstaller build.spec` on macOS.

PyInstaller's binary collection rewrites the LC_RPATH on Mach-O files we
bundle ourselves to `@loader_path/..` — which makes them resolve dylibs
in `Contents/Frameworks/` and shadow-load cv2's older `libtesseract.5`
copy via a symlink there. This script restores `@loader_path` on every
Mach-O file inside `Contents/Frameworks/tesseract/` and `…/poppler/` so
each binary loads its sibling dylibs first.

Usage:
    python tools/fixup_macos_app.py dist/UEEMobileGaragePermits.app
"""

from __future__ import annotations

import os
import subprocess
import sys


def _is_macho(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
    except OSError:
        return False
    # 32/64-bit Mach-O magic numbers (little- and big-endian)
    return magic in {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe",
                     b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce"}


def _fix(path: str) -> None:
    # Replace the bad rpath with @loader_path. Both calls are best-effort.
    subprocess.run(
        ["install_name_tool", "-delete_rpath", "@loader_path/..", path],
        check=False, stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["install_name_tool", "-add_rpath", "@loader_path", path],
        check=False, stderr=subprocess.DEVNULL,
    )
    # Re-sign ad-hoc so Apple Silicon will load the binary. Don't abort the
    # whole fixup if codesign fails on a single dylib — log and continue so
    # the rest of the patches still get applied.
    res = subprocess.run(
        ["codesign", "--force", "--sign", "-", "--timestamp=none", path],
        check=False, stderr=subprocess.PIPE,
    )
    if res.returncode != 0:
        msg = res.stderr.decode("utf-8", errors="replace").strip()
        print(f"[fixup] WARN: codesign failed on {os.path.basename(path)}: {msg}")


_CV2_INIT_STUB = '''\
"""
Replacement cv2/__init__.py for PyInstaller bundles.

Upstream cv2 does `del sys.modules["cv2"]; importlib.import_module("cv2")`
to swap the package for its native extension. Inside a PyInstaller bundle
the frozen importer keeps re-finding the package, triggering the
"recursion is detected" guard. This stub loads cv2.abi3.so directly and
skips that mechanism entirely.
"""
import os
import sys
import importlib.util

_HERE = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
_SO   = os.path.join(_HERE, "cv2.abi3.so")

_spec = importlib.util.spec_from_file_location("cv2", _SO)
_mod  = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Re-export every public name from the native module on this package.
for _k, _v in _mod.__dict__.items():
    if not _k.startswith("_"):
        globals()[_k] = _v

# Some callers do `from cv2 import cv2` — point that submodule at the native.
sys.modules.setdefault("cv2.cv2", _mod)
'''


def _fixup_cv2(app_path: str) -> None:
    """
    cv2's bootstrap is incompatible with PyInstaller's frozen importer
    (recursion error). Replace the bundled __init__.py with a stub that
    loads cv2.abi3.so directly, and ensure the .so is reachable from the
    realpath-resolved __init__.py location.
    """
    fw_so  = os.path.join(app_path, "Contents", "Frameworks", "cv2", "cv2.abi3.so")
    res_so = os.path.join(app_path, "Contents", "Resources", "cv2", "cv2.abi3.so")
    res_init = os.path.join(app_path, "Contents", "Resources", "cv2", "__init__.py")

    if os.path.isfile(fw_so) and not os.path.exists(res_so):
        os.symlink("../../Frameworks/cv2/cv2.abi3.so", res_so)
        print(f"[fixup] symlinked {os.path.relpath(res_so, app_path)}")

    if os.path.isfile(res_init):
        with open(res_init, "w") as f:
            f.write(_CV2_INIT_STUB)
        print(f"[fixup] replaced {os.path.relpath(res_init, app_path)} with stub")


def fixup(app_path: str) -> None:
    fw = os.path.join(app_path, "Contents", "Frameworks")
    if not os.path.isdir(fw):
        sys.exit(f"[fixup] not a .app: {app_path}")

    # Run the cv2 stub patch first so a later binary failure can't skip it.
    _fixup_cv2(app_path)

    targets = [os.path.join(fw, d) for d in ("tesseract", "poppler")]
    fixed = 0
    for d in targets:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            full = os.path.join(d, name)
            if os.path.isfile(full) and _is_macho(full):
                _fix(full)
                fixed += 1
                print(f"[fixup] {os.path.relpath(full, app_path)}")
    print(f"[fixup] patched {fixed} binary/dylib(s)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    fixup(sys.argv[1])
