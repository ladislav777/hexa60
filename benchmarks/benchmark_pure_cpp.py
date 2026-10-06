#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmark_pure_cpp.py — skompiluje benchmark_native.cpp (MSVC /O2) a spusti ho.

Jeden cyklus: najde vcvars64.bat (rovnako ako build_native.py), zbuildi
benchmark_native.exe a spusti ho. Vystup je surova C++ vs C++ tabulka MB/s.
"""
from __future__ import annotations
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPP = os.path.join(ROOT, "benchmarks", "benchmark_native.cpp")
EXE = os.path.join(ROOT, "build_native", "benchmark_native.exe")


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
    return sorted(cands)[-1]


def main() -> int:
    if not os.path.isfile(CPP):
        raise SystemExit(f"chyba: {CPP} neexistuje")
    os.makedirs(os.path.join(ROOT, "build_native"), exist_ok=True)
    vcvars = find_vcvars()
    print(f"[benchmark_pure_cpp] vcvars : {vcvars}")
    print(f"[benchmark_pure_cpp] zdroj  : {CPP}")
    inc = os.path.join(ROOT, "cpp", "include")
    bat = os.path.join(ROOT, "build_native", "build_bench.bat")
    with open(bat, "w", encoding="utf-8") as f:
        f.write("@echo off\r\n")
        f.write(f'call "{vcvars}" >nul\r\n')
        f.write("if errorlevel 1 exit /b 1\r\n")
        f.write(f'cl /nologo /std:c++20 /O2 /EHsc /MD /utf-8 /DNDEBUG /W3 /I"{inc}" '
                f'"{CPP}" /Fe"{EXE}"\r\n')
        f.write("exit /b %ERRORLEVEL%\r\n")
    print("[benchmark_pure_cpp] kompilujem (MSVC /O2) ...")
    rc = subprocess.call(["cmd", "/c", bat], cwd=ROOT)
    if rc != 0 or not os.path.isfile(EXE):
        raise SystemExit(f"[benchmark_pure_cpp] BUILD FAILED (rc={rc})")
    print(f"[benchmark_pure_cpp] OK -> {EXE}")
    print("[benchmark_pure_cpp] spustam cisty C++ benchmark ...")
    print("-" * 80)
    rc = subprocess.call([EXE], cwd=ROOT)
    print("-" * 80)
    print(f"[benchmark_pure_cpp] hotovo (rc={rc})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
