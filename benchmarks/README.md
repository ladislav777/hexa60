# Benchmarks & verification (non-production)

Audit and marketing scripts moved out of the repository root so the root stays a clean Commercial IP Package.

- `verify_integrity.py` — 10,000 SHA-256 round trips (binary / UTF-8 / JSON / CSV / edge cases) + wire footprint 1.375x check.
- `benchmark_encode.py` — HEXA-60 vs Base64 vs Base85 vs Base91 on identical 1/10/100 MB datasets (Python-level methodology).
- `benchmark_pure_cpp.py` + `benchmark_native.cpp` — pure C++ vs C++ shootout (MSVC /O2, same buffers, warm-up, best-of-N).
- `benchmark.py`, `benchmark_ultra.py`, `scaling_benchmark.py`, `verify_reality.py` — older exploratory runs.
- `*_out.txt`, `benchmark_final.txt` — captured logs of the runs above.
- `demo.py`, `generate_linkedin_graphic.py`, `benchmark.jpg/.png` — demo/marketing helpers, not part of the core.
