// ============================================================================
// HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
// Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
//
// PROPRIETARY AND CONFIDENTIAL SOFTWARE.
// Unauthorized copying, distribution, or modification of this file, via any
// medium, is strictly prohibited under applicable copyright laws and B2B EULA.
// ============================================================================

// hexa60/fast_codec.hpp -- L1-Pair-LUT Base-60 codec core (C++20, header-only).
//
// Pure hot-path core used by the nanobind accelerator (_hexa60c). No Python
// dependencies, no exceptions: every error is returned as a small struct that
// hexa60.py translates into the exact same Python exceptions the pure fallback
// raises (InvalidCharacterError / LengthError with identical arguments).
//
// WIRE FORMAT: bit-identical to hexa60.py chunked codec.
//   8 bytes -> 11 chars, tail r (1..7) -> TAIL_CHARS[r] chars.
//
// ARCHITECTURE
// ------------
// * PAIRS[3600] (7200 B, uint16): value % 3600 -> its two Base-60 digits,
//   packed as (high << 8) | low. Halves the division count on encode
//   (11 digits = 5 pair lookups + 1 single instead of 11 divmods).
//   7.2 KB table stays resident in the 32-48 KB L1D cache.
// * DEC[256] (256 B): byte/codepoint -> digit; 0x80 marks "invalid", so
//   validation is a mask test. Lenient counting accumulates branchlessly:
//   valid += (d & 0x80) == 0.
// * 4-way ILP unroll over full chunks: four independent dependency chains so
//   the divider latency of one chunk is hidden by the others.
// * ERROR ORDER mirrors the Python fallback exactly:
//     1. strict character scan   -> BadChar(pos, cp)   [like _prepare]
//     2. layout check (len%11)   -> BadLayout(rem)     [like _REM_FROM_TAIL_CHARS]
//     3. capacity checks         -> Overflow(n_chars, n_bytes) [like _unpack]
//   A lenient decode strips invalid characters FIRST (step 1 counts only),
//   exactly like _prepare(text, strict=False).
#ifndef HEXA60_FAST_CODEC_HPP
#define HEXA60_FAST_CODEC_HPP

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>

namespace hexa60::fast {

inline constexpr char ALPHABET[] =
    "0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-";
static_assert(sizeof(ALPHABET) - 1 == 60, "ALPHABET must be exactly 60 chars");

inline constexpr int BASE = 60;
inline constexpr int CHUNK_BYTES = 8;
inline constexpr int CHUNK_CHARS = 11;
inline constexpr std::uint64_t MAX_U64 = 0xFFFFFFFFFFFFFFFFull;

// TAIL_CHARS[r] for r = 0..7 (index = remaining bytes).
inline constexpr std::uint8_t TAIL_CHARS[8] = {0, 2, 3, 5, 6, 7, 9, 10};

// Residue (n_chars % 11) -> tail bytes. 0x80 marks an invalid residue
// (1, 4, 8 are never produced by TAIL_CHARS).
inline constexpr std::uint8_t REM_TO_BYTES[11] = {
    0, 0x80, 1, 2, 0x80, 3, 4, 5, 0x80, 6, 7};

// ---------------------------------------------------------------------------
// Lookup tables (constexpr, static initialization)
// ---------------------------------------------------------------------------

// PAIRS[x] = two digits of x (0 <= x < 3600): high digit = x / 60,
// low digit = x % 60, packed as (high << 8) | low. 7200 bytes total.
struct PairTable {
    std::uint16_t v[3600];
};
constexpr PairTable make_pairs() {
    PairTable t{};
    for (int x = 0; x < 3600; ++x)
        t.v[x] = static_cast<std::uint16_t>(((x / 60) << 8) | (x % 60));
    return t;
}
inline constexpr PairTable PAIRS = make_pairs();

// DEC[c] = digit 0..59, or 0x80 when c is not in the alphabet (or c > 255,
// which the caller must screen before indexing).
struct DecTable {
    std::uint8_t v[256];
};
constexpr DecTable make_dec() {
    DecTable t{};
    for (int i = 0; i < 256; ++i) t.v[i] = 0x80;
    for (int i = 0; i < 60; ++i)
        t.v[static_cast<unsigned char>(ALPHABET[i])] =
            static_cast<std::uint8_t>(i);
    return t;
}
inline constexpr DecTable DEC = make_dec();

static_assert(PAIRS.v[0] == 0 && PAIRS.v[3599] == ((59u << 8) | 59u));
static_assert(DEC.v[static_cast<unsigned char>('0')] == 0);
static_assert(DEC.v[static_cast<unsigned char>('-')] == 59);
static_assert(DEC.v[static_cast<unsigned char>('I')] == 0x80);

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

enum class Err : int {
    Ok = 0,
    BadChar = 1,     // strict scan: invalid character at pos (code point cp)
    BadLayout = 2,   // len % 11 is not a valid tail residue
    Overflow = 3,    // value does not fit its byte width
};

struct DecResult {
    Err err = Err::Ok;
    std::size_t pos = 0;    // BadChar: index in the original string
    std::uint32_t cp = 0;   // BadChar: code point
    int rem = 0;            // BadLayout: offending residue
    int n_chars = 0;        // Overflow: digit width (11 or tail width)
    int n_bytes = 0;        // Overflow: byte width (8 or tail bytes)
    std::size_t size = 0;   // Ok: bytes written to the output buffer
};

// ---------------------------------------------------------------------------
// Encode
// ---------------------------------------------------------------------------

inline std::size_t encoded_len(std::size_t nbytes) noexcept {
    return (nbytes / CHUNK_BYTES) * CHUNK_CHARS +
           TAIL_CHARS[nbytes % CHUNK_BYTES];
}

inline std::uint64_t load_be64(const std::uint8_t* p) noexcept {
    return (static_cast<std::uint64_t>(p[0]) << 56) |
           (static_cast<std::uint64_t>(p[1]) << 48) |
           (static_cast<std::uint64_t>(p[2]) << 40) |
           (static_cast<std::uint64_t>(p[3]) << 32) |
           (static_cast<std::uint64_t>(p[4]) << 24) |
           (static_cast<std::uint64_t>(p[5]) << 16) |
           (static_cast<std::uint64_t>(p[6]) << 8) |
           static_cast<std::uint64_t>(p[7]);
}

// Write `v` as exactly `width` Base-60 digits (big-endian) into `out`.
// Pair-LUT path: 5 pair lookups + 1 single for width 11.
inline void write_digits(std::uint64_t v, char* out, int width) noexcept {
    int i = width - 1;
    while (i >= 1) {
        const std::uint16_t p = PAIRS.v[v % 3600];
        out[i] = ALPHABET[p & 0xFF];
        out[i - 1] = ALPHABET[p >> 8];
        v /= 3600;
        i -= 2;
    }
    if (i == 0) out[0] = ALPHABET[v];  // v < 60 by the width invariant
}

// `out` must have capacity encoded_len(raw.size()).
inline void encode(std::span<const std::uint8_t> raw, char* out) noexcept {
    const std::size_t n = raw.size();
    const std::size_t full = n / CHUNK_BYTES;
    const std::size_t rem = n % CHUNK_BYTES;
    const std::uint8_t* p = raw.data();
    std::size_t c = 0, o = 0;

    // 4-way ILP unroll: four independent division chains overlap in the
    // out-of-order engine (the latency of `v / 3600` is the critical path).
    for (; c + 4 <= full; c += 4, o += 4 * CHUNK_CHARS) {
        const std::uint64_t v0 = load_be64(p + c * 8);
        const std::uint64_t v1 = load_be64(p + c * 8 + 8);
        const std::uint64_t v2 = load_be64(p + c * 8 + 16);
        const std::uint64_t v3 = load_be64(p + c * 8 + 24);
        write_digits(v0, out + o, CHUNK_CHARS);
        write_digits(v1, out + o + CHUNK_CHARS, CHUNK_CHARS);
        write_digits(v2, out + o + 2 * CHUNK_CHARS, CHUNK_CHARS);
        write_digits(v3, out + o + 3 * CHUNK_CHARS, CHUNK_CHARS);
    }
    for (; c < full; ++c, o += CHUNK_CHARS)
        write_digits(load_be64(p + c * 8), out + o, CHUNK_CHARS);

    if (rem) {
        std::uint64_t v = 0;
        for (std::size_t k = 0; k < rem; ++k)
            v = (v << 8) | p[c * CHUNK_BYTES + k];
        write_digits(v, out + o, TAIL_CHARS[rem]);
    }
}

// ---------------------------------------------------------------------------
// Decode
// ---------------------------------------------------------------------------

// `get(i)` returns the code point at string index i. `out` must have capacity
// >= len (the byte output is always shorter than the character input).
//
// Strict scan runs first (BadChar reported like _prepare), then the layout
// check (BadLayout like the pure residue check), then block decoding with
// capacity checks (Overflow like _unpack). Lenient mode counts valid chars in
// a branchless pass, checks the layout against the CLEANED length and skips
// invalid characters while decoding -- byte-for-byte identical to
// _prepare(text, strict=False) followed by block decoding.
template <class Get>
DecResult decode(std::size_t len, Get&& get, bool strict,
                 std::uint8_t* out) noexcept {
    // --- pass 1: validate (strict) / count valid chars (lenient) ----------
    std::size_t valid = 0;
    if (strict) {
        for (std::size_t i = 0; i < len; ++i) {
            const std::uint32_t cp = get(i);
            const std::uint8_t d = cp < 256 ? DEC.v[cp] : 0x80;
            if (d & 0x80) return DecResult{Err::BadChar, i, cp, 0, 0, 0, 0};
        }
        valid = len;
    } else {
        for (std::size_t i = 0; i < len; ++i) {
            const std::uint32_t cp = get(i);
            const std::uint8_t d = cp < 256 ? DEC.v[cp] : 0x80;
            valid += (d & 0x80) == 0;  // branchless count
        }
    }
    if (valid == 0) return DecResult{};  // empty (== pure: clean is empty)

    const std::size_t full = valid / CHUNK_CHARS;
    const int rem = static_cast<int>(valid % CHUNK_CHARS);
    const std::uint8_t tail_bytes = REM_TO_BYTES[rem];
    if (tail_bytes & 0x80)
        return DecResult{Err::BadLayout, 0, 0, rem, 0, 0, 0};

    // --- pass 2: digit stream ---------------------------------------------
    std::size_t idx = 0;
    auto next_digit = [&]() noexcept -> int {
        while (idx < len) {
            const std::uint32_t cp = get(idx++);
            const std::uint8_t d = cp < 256 ? DEC.v[cp] : 0x80;
            if ((d & 0x80) == 0) return d;  // strict: always true (pass 1)
        }
        return -1;  // unreachable: `valid` digits were counted above
    };

    std::size_t o = 0;
    for (std::size_t b = 0; b < full; ++b) {
        std::uint64_t acc = 0;
        bool ovf = false;
        for (int k = 0; k < CHUNK_CHARS; ++k) {
            const int d = next_digit();
            // acc <= 60^10 - 1 before the 11th step, and 60^10 > 2^64 / 60,
            // so overflow is possible exactly at the last digit.
            if (k == CHUNK_CHARS - 1)
                ovf = acc > (MAX_U64 - static_cast<std::uint64_t>(d)) / 60;
            acc = acc * 60 + static_cast<std::uint64_t>(d);
        }
        if (ovf)
            return DecResult{Err::Overflow, 0, 0, 0, CHUNK_CHARS, CHUNK_BYTES, 0};
        for (int k = CHUNK_BYTES - 1; k >= 0; --k) {
            out[o + static_cast<std::size_t>(k)] =
                static_cast<std::uint8_t>(acc);
            acc >>= 8;
        }
        o += CHUNK_BYTES;
    }

    if (rem) {
        std::uint64_t acc = 0;
        for (int k = 0; k < rem; ++k)
            acc = acc * 60 + static_cast<std::uint64_t>(next_digit());
        // Tail value must fit its byte width (== pure _unpack OverflowError).
        if (acc >= (static_cast<std::uint64_t>(1) << (8 * tail_bytes)))
            return DecResult{Err::Overflow, 0, 0, 0, rem, tail_bytes, 0};
        for (int k = tail_bytes - 1; k >= 0; --k) {
            out[o + static_cast<std::size_t>(k)] =
                static_cast<std::uint8_t>(acc);
            acc >>= 8;
        }
        o += tail_bytes;
    }

    return DecResult{Err::Ok, 0, 0, 0, 0, 0, o};
}

}  // namespace hexa60::fast

#endif  // HEXA60_FAST_CODEC_HPP



