# hexa60-core (Rust)

Official Rust port of the HEXA-60 chunked codec — bit-identical to
`hexa60.py` (`encode_chunked` / `decode_chunked_auto`) and
`cpp/include/hexa60/codec.hpp`: 8 bytes -> 11 chars, tail `TAIL_CHARS[r]`
chars for `r` leftover bytes, 1.375x wire expansion.

## Verify

```powershell
cd core-rust
cargo test --release
```

Expected: all unit tests pass (`ok`, 0 failed).

## Cross-check against Python (bit identity)

```powershell
# from the repo root; prints identical wire strings for sample vectors
python -c "import hexa60; print(hexa60.encode_chunked(bytes(range(256))[:17])))"
```

The same input encoded with `hexa60_core::encode_chunked` must produce
the identical string. Any mismatch is a release-blocking bug.
