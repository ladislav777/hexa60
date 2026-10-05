// ============================================================================
// HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
// Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
//
// PROPRIETARY AND CONFIDENTIAL SOFTWARE.
// Unauthorized copying, distribution, or modification of this file, via any
// medium, is strictly prohibited under applicable copyright laws and B2B EULA.
// ============================================================================

// hexa60/codec.hpp -- header-only Base-60 binary-to-text codec.
//
// C++20 port of the reference Python implementation (hexa60.py).
// Zero dependencies beyond the STL.
//
// WIRE FORMAT (must stay bit-identical to the Python reference):
//   ALPHABET = "0123456789ABCDEFGHIJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-"
//   8 bytes -> 11 chars, tail r in 1..7 -> TAIL_CHARS[r] chars
//
// THREE FACTS THAT ARE EASY TO GET WRONG -- read before modifying:
//
// 1. TAIL_CHARS is {0,2,3,5,6,7,9,10} for r = 0..7.
//    Derived: ceil(r * 8 / log2(60)). Note r=5 is 7, NOT 8.
//    60^6 = 2.176e10 < 2^40 (the 5-byte capacity) but 60^7 = 2.799e12 >=
//    2^40, so 7 is the minimum. Using 8 would waste a character and break
//    length recovery from len(text) % 11.
//
// 2. 60^11 = 3.628e19 > 2^64 = 1.845e19.
//    The 11-character space is WIDER than the 8-byte space it encodes, so
//    roughly half of all 11-char strings are NOT representable as 8 bytes.
//    Decoding such a string must throw -- it must NEVER be silently
//    truncated. This is the most important safety property of this file.
//
// 3. Residues of TAIL_CHARS modulo 11 are {0,2,3,5,6,7,9,10} -- all
//    unique, so the tail length is recoverable from len(text) % 11.
//    Residues 1, 4 and 8 are invalid and must throw.

#ifndef HEXA60_CODEC_HPP
#define HEXA60_CODEC_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace hexa60 {

// ---------------------------------------------------------------------------
// Core constants
// ---------------------------------------------------------------------------
inline constexpr char ALPHABET[] =
    "0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz_-";
static_assert(sizeof(ALPHABET) - 1 == 60, "ALPHABET must be exactly 60 characters");
static_assert(ALPHABET[58] == '_', "ALPHABET[58] must be '_'");
static_assert(ALPHABET[59] == '-', "ALPHABET[59] must be '-'");
inline constexpr std::size_t BASE = 60;
inline constexpr std::size_t ALPHABET_SIZE = 60;

inline constexpr std::size_t CHUNK_BYTES = 8;
inline constexpr std::size_t CHUNK_CHARS = 11;

// TAIL_CHARS[r] = characters needed to encode r trailing bytes.
// Derived: C = ceil(r * 8 / log2(60)). Index = remaining BYTES.
inline constexpr std::array<std::size_t, 8> TAIL_CHARS = {0, 2, 3, 5, 6, 7, 9, 10};

inline constexpr std::size_t INVALID_TAIL = 99;

// Reverse map: tail char count -> byte count. INVALID_TAIL when impossible.
//
// Derived from TAIL_CHARS by inversion, NOT written by hand:
//   TAIL_CHARS = {0,2,3,5,6,7,9,10} for r = 0..7 bytes
//   so residue 0 -> 0, 2 -> 1, 3 -> 2, 5 -> 3, 6 -> 4, 7 -> 5, 9 -> 6, 10 -> 7
//   residues 1, 4, 8 are NOT produced and are INVALID.
//
// NOTE: this is exactly the hand-written table the original port got wrong
// (it had 5 marked invalid and 3 mapped from 9). Verify with static_asserts
// below -- the inversion is machine-checked, not trusted.
inline constexpr std::array<std::size_t, CHUNK_CHARS + 1> REM_FROM_TAIL_CHARS = {
    /*  0 */ 0,   // 0  chars -> 0 bytes (no tail)
    /*  1 */ INVALID_TAIL,  // never produced
    /*  2 */ 1,
    /*  3 */ 2,
    /*  4 */ INVALID_TAIL,  // never produced
    /*  5 */ 3,
    /*  6 */ 4,
    /*  7 */ 5,
    /*  8 */ INVALID_TAIL,  // never produced
    /*  9 */ 6,
    /* 10 */ 7,
    /* 11 */ INVALID_TAIL,  // full-chunk residue, never passed to the tail path
};

/// Compile-time proof that REM_FROM_TAIL_CHARS is the exact inverse of
/// TAIL_CHARS, and that no residue is claimed twice.
constexpr bool tail_tables_are_consistent() {
    for (std::size_t r = 0; r < 8; ++r) {
        const std::size_t chars = TAIL_CHARS[r];
        if (chars > CHUNK_CHARS) return false;
        if (REM_FROM_TAIL_CHARS[chars] != r) return false;
    }
    // every residue 0..10 must be claimed at most once
    for (std::size_t a = 0; a < CHUNK_CHARS; ++a) {
        if (REM_FROM_TAIL_CHARS[a] == INVALID_TAIL) continue;
        for (std::size_t b = a + 1; b <= CHUNK_CHARS; ++b) {
            if (REM_FROM_TAIL_CHARS[b] != INVALID_TAIL &&
                REM_FROM_TAIL_CHARS[b] == REM_FROM_TAIL_CHARS[a]) {
                return false;  // duplicate mapping -> length is ambiguous
            }
        }
    }
    return true;
}
static_assert(tail_tables_are_consistent(),
              "REM_FROM_TAIL_CHARS must invert TAIL_CHARS with unique residues");

// ---------------------------------------------------------------------------
// constexpr lookup table: byte value -> digit index, 0xFF when invalid.
// ---------------------------------------------------------------------------
constexpr std::array<std::uint8_t, 256> make_lookup() {
    std::array<std::uint8_t, 256> t{};
    for (auto& e : t) e = 0xFF;
    for (std::size_t i = 0; i < ALPHABET_SIZE; ++i) {
        t[static_cast<std::uint8_t>(ALPHABET[i])] = static_cast<std::uint8_t>(i);
    }
    return t;
}

inline constexpr std::array<std::uint8_t, 256> LOOKUP = make_lookup();

/// Compile-time proof that the alphabet has 60 DISTINCT characters. A duplicated
/// character would silently corrupt the lookup table, so this must hold.
constexpr bool alphabet_has_no_duplicates() {
    for (std::size_t i = 0; i < ALPHABET_SIZE; ++i) {
        for (std::size_t j = i + 1; j < ALPHABET_SIZE; ++j) {
            if (ALPHABET[i] == ALPHABET[j]) return false;
        }
    }
    return true;
}
static_assert(alphabet_has_no_duplicates(), "ALPHABET contains a duplicate character");

/// Compile-time proof that every alphabet character is non-negative ASCII, so
/// indexing LOOKUP by (unsigned char) is well defined on all platforms.
constexpr bool alphabet_is_plain_ascii() {
    for (std::size_t i = 0; i < ALPHABET_SIZE; ++i) {
        if (static_cast<unsigned char>(ALPHABET[i]) > 127) return false;
    }
    return true;
}
static_assert(alphabet_is_plain_ascii(), "ALPHABET must be plain ASCII");

constexpr bool is_alphabet_char(char c) noexcept {
    return LOOKUP[static_cast<std::uint8_t>(c)] != 0xFF;
}

constexpr std::uint8_t digit_of(char c) noexcept {
    return LOOKUP[static_cast<std::uint8_t>(c)];
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------
/// Character outside ALPHABET. Carries the position, mirroring Python's
/// InvalidCharacterError.
class InvalidCharacterError : public std::invalid_argument {
public:
    InvalidCharacterError(char c, std::size_t pos)
        : std::invalid_argument(build(c, pos)), char_(c), position_(pos) {}

    [[nodiscard]] char character() const noexcept { return char_; }
    [[nodiscard]] std::size_t position() const noexcept { return position_; }

private:
    static std::string build(char c, std::size_t pos) {
        std::string m = "Invalid HEXA60 character '";
        m += c;
        m += "' at position ";
        m += std::to_string(pos);
        return m;
    }
    char char_;
    std::size_t position_;
};

/// Invalid total length, or a chunk/tail whose value exceeds its byte width.
class LengthError : public std::out_of_range {
public:
    explicit LengthError(const std::string& what) : std::out_of_range(what) {}
};

namespace detail {

/// Write exactly `width` base-60 digits of `value`, MSB first.
inline void write_fixed(std::uint64_t value, std::size_t width, char* out) noexcept {
    for (std::size_t i = width; i-- > 0;) {
        out[i] = ALPHABET[value % BASE];
        value /= BASE;
    }
}

/// Read a base-60 block of `nchars` characters. Throws on a bad character or
/// on a value that would exceed UINT64_MAX. The overflow check happens BEFORE
/// the multiply, so no wrap-around is possible.
inline std::uint64_t read_block(const char* p, std::size_t nchars, std::size_t abs_pos) {
    std::uint64_t num = 0;
    for (std::size_t i = 0; i < nchars; ++i) {
        const std::uint8_t d = digit_of(p[i]);
        if (d == 0xFF) {
            throw InvalidCharacterError(p[i], abs_pos + i);
        }
        if (num > (UINT64_MAX - d) / BASE) {
            throw LengthError("HEXA60 block '" + std::string(p, nchars) +
                              "' exceeds the capacity of its byte width");
        }
        num = num * BASE + d;
    }
    return num;
}

}  // namespace detail

// ---------------------------------------------------------------------------
// encode
// ---------------------------------------------------------------------------

/// Encode raw bytes to a Base-60 string. Empty input yields an empty string.
[[nodiscard]] inline std::string encode(const std::uint8_t* data, std::size_t size) {
    if (size == 0) return {};

    std::string out;
    out.reserve(size / CHUNK_BYTES * CHUNK_CHARS + CHUNK_CHARS);

    const std::size_t end = size - size % CHUNK_BYTES;

    for (std::size_t i = 0; i < end; i += CHUNK_BYTES) {
        std::uint64_t v = 0;
        for (std::size_t k = 0; k < CHUNK_BYTES; ++k) {
            v = (v << 8) | data[i + k];
        }
        // 11 chars always suffice: any 8-byte value is < 2^64 < 60^11.
        char buf[CHUNK_CHARS];
        detail::write_fixed(v, CHUNK_CHARS, buf);
        out.append(buf, CHUNK_CHARS);
    }

    const std::size_t tail = size - end;
    if (tail != 0) {
        std::uint64_t v = 0;
        for (std::size_t k = 0; k < tail; ++k) {
            v = (v << 8) | data[end + k];
        }
        const std::size_t width = TAIL_CHARS[tail];
        char buf[CHUNK_CHARS];
        detail::write_fixed(v, width, buf);
        out.append(buf, width);
    }

    return out;
}

[[nodiscard]] inline std::string encode(std::span<const std::uint8_t> s) {
    return encode(s.data(), s.size());
}

[[nodiscard]] inline std::string encode(const std::vector<std::uint8_t>& v) {
    return encode(v.data(), v.size());
}

[[nodiscard]] inline std::string encode(std::string_view raw) {
    return encode(reinterpret_cast<const std::uint8_t*>(raw.data()), raw.size());
}

// ---------------------------------------------------------------------------
// decode
// ---------------------------------------------------------------------------

/// Decode a Base-60 string back to bytes.
///
/// Throws InvalidCharacterError for a byte outside ALPHABET, and LengthError
/// for a total length that is not a valid chunk layout or for a block/tail
/// whose value does not fit its byte width.
[[nodiscard]] inline std::vector<std::uint8_t> decode(std::string_view s) {
    std::vector<std::uint8_t> out;
    if (s.empty()) return out;

    const std::size_t n_full = s.size() / CHUNK_CHARS;
    const std::size_t rem = s.size() % CHUNK_CHARS;

    if (rem != 0) {
        if (REM_FROM_TAIL_CHARS[rem] == INVALID_TAIL) {
            throw LengthError("Invalid HEXA60 length " + std::to_string(s.size()) +
                              "; residue " + std::to_string(rem) + " mod " +
                              std::to_string(CHUNK_CHARS) + " is not a valid tail");
        }
    }

    out.reserve(n_full * CHUNK_BYTES + (rem ? REM_FROM_TAIL_CHARS[rem] : 0));

    for (std::size_t i = 0; i < n_full; ++i) {
        const std::size_t off = i * CHUNK_CHARS;
        const std::uint64_t v = detail::read_block(s.data() + off, CHUNK_CHARS, off);
        for (std::size_t k = CHUNK_BYTES; k-- > 0;) {
            out.push_back(static_cast<std::uint8_t>(v >> (k * 8)));
        }
    }

    if (rem != 0) {
        const std::size_t off = n_full * CHUNK_CHARS;
        const std::size_t nbytes = REM_FROM_TAIL_CHARS[rem];
        const std::uint64_t v = detail::read_block(s.data() + off, rem, off);
        // A tail needing more bytes than its width implies is REJECTED,
        // never truncated.
        if (v >= (std::uint64_t{1} << (8 * nbytes))) {
            throw LengthError("HEXA60 tail '" + std::string(s.data() + off, rem) +
                              "' does not fit in " + std::to_string(nbytes) + " byte(s)");
        }
        for (std::size_t k = nbytes; k-- > 0;) {
            out.push_back(static_cast<std::uint8_t>(v >> (k * 8)));
        }
    }

    return out;
}

// ---------------------------------------------------------------------------
// validation helpers
// ---------------------------------------------------------------------------

/// True if every character of `s` is in ALPHABET. Empty is valid (zero bytes).
[[nodiscard]] inline bool is_valid(std::string_view s) noexcept {
    for (const char c : s) {
        if (!is_alphabet_char(c)) return false;
    }
    return true;
}

/// True if `n` is a valid chunked length.
[[nodiscard]] inline bool is_valid_length(std::size_t n) noexcept {
    const std::size_t rem = n % CHUNK_CHARS;
    return rem == 0 || REM_FROM_TAIL_CHARS[rem] != INVALID_TAIL;
}

}  // namespace hexa60

#endif  // HEXA60_CODEC_HPP
