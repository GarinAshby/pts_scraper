"""
tools/macos_bundle.py
=====================
Copy a macOS binary plus all of its non-system dylib dependencies into a
single flat directory, rewriting install names so the directory is
relocatable (no /opt/homebrew runtime dependency).

Strategy
--------
- All binaries and dylibs land in ONE flat directory.
- Each .dylib's LC_ID_DYLIB → @rpath/<basename>
- Every LC_LOAD_DYLIB referencing a non-system path → @rpath/<basename>
- Each binary/dylib gets LC_RPATH = @loader_path, so @rpath resolves
  to the file's own directory.

Usage
-----
    python tools/macos_bundle.py <dest_dir> <binary> [<binary> ...]
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys


def _is_system(path: str) -> bool:
    return path.startswith("/usr/lib/") or path.startswith("/System/")


def _otool_deps(binary: str) -> list[str]:
    out = subprocess.check_output(["otool", "-L", binary], text=True)
    deps: list[str] = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        path = line.split(" (")[0].strip()
        if path:
            deps.append(path)
    return deps


def _resolve(dep: str) -> str | None:
    """Resolve absolute / @rpath / @loader_path references to a real file."""
    if os.path.isabs(dep) and os.path.isfile(dep):
        return os.path.realpath(dep)
    if dep.startswith("@rpath/"):
        rel = dep[len("@rpath/"):]
        for prefix in ("/opt/homebrew/lib", "/usr/local/lib", "/opt/homebrew/opt"):
            cand = os.path.join(prefix, rel)
            if os.path.isfile(cand):
                return os.path.realpath(cand)
    return None


def _make_writable(path: str) -> None:
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRUSR)


def _collect(binary: str, dest_dir: str, copied: set[str]) -> None:
    real = os.path.realpath(binary)
    for dep in _otool_deps(real):
        if _is_system(dep):
            continue
        src = _resolve(dep)
        if src is None:
            print(f"[bundle] WARN: unresolved {dep}")
            continue
        # Use the SONAME as referenced (e.g. libzstd.1.dylib), not the
        # realpath basename (e.g. libzstd.1.5.7.dylib). Other libs link
        # against the abbreviated name.
        ref_name = os.path.basename(dep)
        dest = os.path.join(dest_dir, ref_name)
        if dest in copied or ref_name == os.path.basename(real):
            continue
        copied.add(dest)
        if not os.path.isfile(dest):
            shutil.copy2(src, dest)
            _make_writable(dest)
            print(f"[bundle]   + {ref_name}")
        _collect(src, dest_dir, copied)


def _rewrite(path: str) -> None:
    name = os.path.basename(path)
    is_dylib = name.endswith(".dylib") or ".dylib." in name

    if is_dylib:
        subprocess.run(
            ["install_name_tool", "-id", f"@rpath/{name}", path],
            check=True,
        )

    for dep in _otool_deps(path):
        if _is_system(dep):
            continue
        if dep.startswith("@loader_path/") or dep.startswith("@executable_path/"):
            continue
        dep_name = os.path.basename(dep)
        if dep_name == name:
            continue  # self
        # Already @rpath-relative? Still rewrite to normalise the basename
        new = f"@rpath/{dep_name}"
        if dep == new:
            continue
        subprocess.run(
            ["install_name_tool", "-change", dep, new, path],
            check=True,
        )

    # Add @loader_path as an rpath. Idempotent: if it already exists,
    # install_name_tool errors — we swallow that.
    subprocess.run(
        ["install_name_tool", "-add_rpath", "@loader_path", path],
        check=False,
        stderr=subprocess.DEVNULL,
    )

    # On Apple Silicon, install_name_tool invalidates the code signature and
    # the loader (amfid) will SIGKILL the binary at exec time. Re-sign ad-hoc.
    subprocess.run(
        ["codesign", "--force", "--sign", "-", "--timestamp=none", path],
        check=True,
        stderr=subprocess.DEVNULL,
    )


def bundle(binaries: list[str], dest_dir: str) -> None:
    os.makedirs(dest_dir, exist_ok=True)
    copied: set[str] = set()

    for src in binaries:
        real = os.path.realpath(src)
        dest = os.path.join(dest_dir, os.path.basename(src))
        shutil.copy2(real, dest)
        _make_writable(dest)
        copied.add(dest)
        print(f"[bundle] + {os.path.basename(src)} (entry)")
        _collect(real, dest_dir, copied)

    for path in sorted(copied):
        _rewrite(path)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    bundle(sys.argv[2:], sys.argv[1])
