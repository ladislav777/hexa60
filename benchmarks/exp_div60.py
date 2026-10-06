"""Spusti benchmarks/exp_div60.cpp (len meranie, bez zasahu do jadra)."""
import os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "benchmarks", "exp_div60.cpp")
INC = os.path.join(ROOT, "cpp", "include")
EXE = os.path.join(ROOT, "benchmarks", "exp_div60.exe")


def find_vcvars():
    import glob
    cands = []
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        cands += glob.glob(os.path.join(base, "Microsoft Visual Studio", "*",
                                        "*", "VC", "Auxiliary", "Build", "vcvars64.bat"))
    if not cands:
        raise SystemExit("vcvars64.bat nenajdeny")
    return cands[0]


def main():
    vc = find_vcvars()
    cmd = (f'"{vc}" >nul && cl /nologo /std:c++20 /O2 /I"{INC}" '
           f'"{SRC}" /Fe"{EXE}" /Fo"{os.path.join(ROOT, "benchmarks")}\\"')
    r = subprocess.run(cmd, shell=True, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit("kompilacia zlyhala")
    r = subprocess.run([EXE], cwd=ROOT)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
