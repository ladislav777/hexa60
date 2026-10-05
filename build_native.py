#!/usr/bin/env python

# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

"""Build the _hexa60c native accelerator (MSVC, no CMake required).

Usage:
    python build_native.py

The script locates vcvars64.bat (preferring the newest MSVC toolset),
compiles cpp/nanobind/bindings.cpp together with nanobind's amalgamated
nb_combined.cpp and links _hexa60c.pyd next to hexa60.py.

After a successful build, hexa60.py picks the module up automatically
(set HEXA60_PURE=1 to force the pure-Python fallback).
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import sysconfig

ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(ROOT, "build_native")


def find_nanobind():
    import nanobind

    root = os.path.dirname(nanobind.__file__)
    inc = os.path.join(root, "include")
    combined = os.path.join(root, "src", "nb_combined.cpp")
    robin = os.path.join(root, "ext", "robin_map", "include")
    if not os.path.isfile(combined):
        raise SystemExit(f"nanobind nb_combined.cpp not found: {combined}")
    return inc, combined, robin if os.path.isdir(robin) else None


def msvc_toolset_version(vcvars: str) -> tuple[int, ...]:
    # <VS>/VC/Auxiliary/Build/vcvars64.bat -> <VS>/VC/Tools/MSVC/<ver>
    vc_dir = os.path.dirname(os.path.dirname(os.path.dirname(vcvars)))
    vers = glob.glob(os.path.join(vc_dir, "Tools", "MSVC", "*"))
    best: tuple[int, ...] = ()
    for v in vers:
        try:
            t = tuple(int(x) for x in os.path.basename(v).split("."))
        except ValueError:
            continue
        if t > best:
            best = t
    return best


def find_vcvars() -> str:
    cands = glob.glob(
        r"C:\Program Files (x86)\Microsoft Visual Studio\*\*"
        r"\VC\Auxiliary\Build\vcvars64.bat"
    ) + glob.glob(
        r"C:\Program Files\Microsoft Visual Studio\*\*"
        r"\VC\Auxiliary\Build\vcvars64.bat"
    )
    if not cands:
        raise SystemExit("vcvars64.bat not found - install Visual Studio Build Tools")
    cands.sort(key=msvc_toolset_version, reverse=True)
    return cands[0]


def python_lib_dir() -> str:
    return os.path.join(sys.prefix, "libs")


def python_lib_name() -> str:
    # The import library is pythonXY.lib; LDLIBRARY on Windows is the DLL.
    return f"python{sys.version_info[0]}{sys.version_info[1]}.lib"


def main() -> None:
    vcvars = find_vcvars()
    nb_inc, nb_combined, robin = find_nanobind()
    ext = sysconfig.get_config_var("EXT_SUFFIX") or ".pyd"
    out = os.path.join(ROOT, f"_hexa60c{ext}")
    os.makedirs(BUILD_DIR, exist_ok=True)

    py_inc = sysconfig.get_paths()["include"]
    includes = f'/I"{py_inc}" /I"{nb_inc}" /I"{os.path.join(ROOT, "cpp", "include")}"'
    if robin:
        includes += f' /I"{robin}"'

    py_lib_dir = python_lib_dir()
    py_lib = python_lib_name()
    flags = "/nologo /std:c++20 /O2 /EHsc /MD /utf-8 /DNDEBUG /W3"
    bindings = os.path.join(ROOT, "cpp", "nanobind", "bindings.cpp")
    obj_b = os.path.join(BUILD_DIR, "bindings.obj")
    obj_n = os.path.join(BUILD_DIR, "nb_combined.obj")

    # Each source is compiled in its own cl invocation with an explicit
    # /Fo<file> (a /Fo directory ending in a backslash breaks cmd quoting),
    # then both objects are linked into the extension.
    bat_lines = [
        "@echo off",
        f'call "{vcvars}" >nul',
        "if errorlevel 1 exit /b 1",
        f"cl {flags} {includes} /c \"{bindings}\" /Fo\"{obj_b}\"",
        "if errorlevel 1 exit /b 1",
    ]
    # Reuse nb_combined.obj when it is newer than the nanobind source:
    # recompiling it costs minutes, and it does not depend on our header.
    if not (os.path.isfile(obj_n) and
            os.path.getmtime(obj_n) >= os.path.getmtime(nb_combined)):
        bat_lines += [
            f"cl {flags} {includes} /c \"{nb_combined}\" /Fo\"{obj_n}\"",
            "if errorlevel 1 exit /b 1",
        ]
    bat_lines += [
        f'link /nologo /DLL /OUT:"{out}" /IMPLIB:"{os.path.join(BUILD_DIR, "_hexa60c.lib")}" '
        f'"{obj_b}" "{obj_n}" /LIBPATH:"{py_lib_dir}" {py_lib}',
        "exit /b %ERRORLEVEL%",
    ]
    bat = os.path.join(BUILD_DIR, "build.bat")
    with open(bat, "w", encoding="utf-8") as f:
        f.write("\r\n".join(bat_lines) + "\r\n")

    print(f"[build_native] vcvars : {vcvars}")
    print(f"[build_native] output : {out}")
    log = os.path.join(BUILD_DIR, "build.log")
    with open(log, "w", encoding="utf-8") as lf:
        rc = subprocess.call(["cmd", "/c", bat], stdout=lf, stderr=subprocess.STDOUT,
                             cwd=ROOT)
    if rc != 0 or not os.path.isfile(out):
        print(f"[build_native] FAILED (rc={rc}), see {log}")
        raise SystemExit(rc or 1)
    print(f"[build_native] OK -> {out}")


if __name__ == "__main__":
    main()
