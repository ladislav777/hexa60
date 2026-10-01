// hexa60/int.hpp -- immutable Base-60 integer with full arithmetic.
//
// C++20 port of base60_int.py / base60_arithmetic.py.
//
// *** READ THIS BEFORE USING THE SIGN FEATURE ***
//
// '-' is NOT a sign character in the HEXA60 alphabet. It is ALPHABET[59],
// the 60th digit, with the value 59. Using a leading '-' as a sign makes the
// representation ambiguous: "-5" could mean -5, or the two-digit number
// 59*60 + 5 = 3545.
//
// This port therefore splits the two concerns:
//   * from_string(s)         -- wire-compatible, '-' is a DIGIT (59).
//   * from_string_signed(s)  -- opt-in, a leading '-' is a SIGN. Round-trips
//                               with to_signed_string() only, and is NOT
//                               wire-compatible with from_string().
//
// to_b60() is always the unsigned, wire-compatible form.
//
// Magnitude is uint64_t. 60^11 > 2^64, so a 12-digit Base-60 number can
// overflow; parse and arithmetic throw OverflowError rather than wrapping.

#ifndef HEXA60_INT_HPP
#define HEXA60_INT_HPP

#include <algorithm>
#include <compare>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "hexa60/codec.hpp"

namespace hexa60 {

/// Value cannot be represented in 64 bits of magnitude.
class OverflowError : public std::out_of_range {
public:
    explicit OverflowError(const std::string& what) : std::out_of_range(what) {}
};

/// Immutable value type. Arithmetic never mutates; every operation returns a
/// new instance.
class Base60Int {
public:
    // -- construction -----------------------------------------------------
    constexpr Base60Int() = default;
    // NOTE: a single signed/unsigned constructor pair would make
    // Base60Int(-10) ambiguous. Both overloads are non-explicit on purpose so
    // that Base60Int(-10) picks int64_t (exact) rather than uint64_t (wrap).
    constexpr explicit Base60Int(std::uint64_t v) noexcept : value_(v) {}
    Base60Int(std::int64_t v) noexcept
        : value_(v < 0 ? (~static_cast<std::uint64_t>(v) + 1)
                       : static_cast<std::uint64_t>(v)),
          negative_(v < 0) {}
    Base60Int(int v) noexcept
        : Base60Int(static_cast<std::int64_t>(v)) {}

    Base60Int(const Base60Int&) = default;
    Base60Int(Base60Int&&) = default;
    Base60Int& operator=(const Base60Int&) = default;
    Base60Int& operator=(Base60Int&&) = default;
    ~Base60Int() = default;

    /// Parse a Base-60 string. '-' is treated as the DIGIT 59, matching the
    /// wire format. Throws InvalidCharacterError for a bad character,
    /// std::invalid_argument for an empty string, OverflowError if the value
    /// does not fit in 64 bits.
    [[nodiscard]] static Base60Int from_string(std::string_view s) {
        if (s.empty()) {
            throw std::invalid_argument("Base60Int: empty string is not a number");
        }
        std::uint64_t v = 0;
        for (std::size_t i = 0; i < s.size(); ++i) {
            const std::uint8_t d = digit_of(s[i]);
            if (d == 0xFF) {
                throw InvalidCharacterError(s[i], i);
            }
            if (v > (std::numeric_limits<std::uint64_t>::max() - d) / BASE) {
                throw OverflowError("Base60Int: value '" + std::string(s) +
                                    "' exceeds 64-bit magnitude");
            }
            v = v * BASE + d;
        }
        return Base60Int(v);
    }

    /// Opt-in: a leading '-' is a SIGN. Not wire-compatible.
    [[nodiscard]] static Base60Int from_string_signed(std::string_view s) {
        bool neg = false;
        if (!s.empty() && s.front() == '-') {
            neg = true;
            s.remove_prefix(1);
            if (s.empty()) {
                throw std::invalid_argument("Base60Int: sign with no digits");
            }
        }
        Base60Int r = from_string(s);
        if (neg) r.negative_ = r.value_ != 0;
        return r;
    }

    /// Build from a big-endian byte buffer. Empty yields zero.
    [[nodiscard]] static Base60Int from_bytes(const std::uint8_t* data, std::size_t n) {
        std::uint64_t v = 0;
        for (std::size_t i = 0; i < n; ++i) {
            if (v > (std::numeric_limits<std::uint64_t>::max() >> 8)) {
                throw OverflowError("Base60Int: byte buffer exceeds 64 bits");
            }
            v = (v << 8) | data[i];
        }
        return Base60Int(v);
    }

    // -- conversion -------------------------------------------------------
    /// Canonical unsigned Base-60 string, no leading zeros, no sign.
    [[nodiscard]] std::string to_b60() const {
        if (value_ == 0) return std::string(1, ALPHABET[0]);
        std::string out;
        std::uint64_t v = value_;
        while (v) {
            out += ALPHABET[v % BASE];
            v /= BASE;
        }
        std::reverse(out.begin(), out.end());
        return out;
    }

    /// Signed form; identical to to_b60() for non-negative values.
    [[nodiscard]] std::string to_signed_string() const {
        if (!is_negative()) return to_b60();
        return "-" + to_b60();
    }

    [[nodiscard]] constexpr std::uint64_t to_uint64() const noexcept { return value_; }
    [[nodiscard]] std::int64_t to_int64() const noexcept {
        return is_negative() ? -static_cast<std::int64_t>(value_)
                              : static_cast<std::int64_t>(value_);
    }
    [[nodiscard]] constexpr bool is_negative() const noexcept {
        return negative_ && value_ != 0;
    }
    [[nodiscard]] constexpr bool is_zero() const noexcept { return value_ == 0; }

    /// Digits MSB first. Zero yields {0}.
    [[nodiscard]] std::vector<std::uint8_t> digits() const {
        std::vector<std::uint8_t> out;
        if (value_ == 0) {
            out.push_back(0);
            return out;
        }
        std::uint64_t v = value_;
        while (v) {
            out.push_back(static_cast<std::uint8_t>(v % BASE));
            v /= BASE;
        }
        std::reverse(out.begin(), out.end());
        return out;
    }

    // -- arithmetic -------------------------------------------------------
    [[nodiscard]] Base60Int operator-() const { return from_parts(value_, !negative_); }

    [[nodiscard]] friend Base60Int operator+(const Base60Int& a, const Base60Int& b) {
        if (a.negative_ == b.negative_) {
            return from_parts(check_add(a.value_, b.value_), a.negative_);
        }
        // Opposite signs -> magnitude difference, sign of the larger.
        if (a.value_ >= b.value_) {
            return from_parts(a.value_ - b.value_, a.negative_);
        }
        return from_parts(b.value_ - a.value_, b.negative_);
    }

    [[nodiscard]] friend Base60Int operator-(const Base60Int& a, const Base60Int& b) {
        return a + Base60Int::from_parts(b.value_, !b.negative_);
    }

    [[nodiscard]] friend Base60Int operator*(const Base60Int& a, const Base60Int& b) {
        if (a.value_ == 0 || b.value_ == 0) return Base60Int(0);
        if (a.value_ > std::numeric_limits<std::uint64_t>::max() / b.value_) {
            throw OverflowError("Base60Int: multiplication overflows 64 bits");
        }
        return from_parts(a.value_ * b.value_, a.negative_ != b.negative_);
    }

    /// Truncating division (C++ / semantics). std::domain_error on zero.
    [[nodiscard]] friend Base60Int operator/(const Base60Int& a, const Base60Int& b) {
        if (b.value_ == 0) {
            throw std::domain_error("Base60Int: division by zero");
        }
        return from_parts(a.value_ / b.value_, a.negative_ != b.negative_);
    }

    /// Remainder; the sign follows the dividend (C++ and Python semantics).
    [[nodiscard]] friend Base60Int operator%(const Base60Int& a, const Base60Int& b) {
        if (b.value_ == 0) {
            throw std::domain_error("Base60Int: modulo by zero");
        }
        return from_parts(a.value_ % b.value_, a.negative_);
    }

    /// Floor division: rounds toward negative infinity, unlike operator/.
    [[nodiscard]] friend Base60Int div_floor(const Base60Int& a, const Base60Int& b) {
        if (b.value_ == 0) {
            throw std::domain_error("Base60Int: division by zero");
        }
        const std::uint64_t q = a.value_ / b.value_;
        const std::uint64_t r = a.value_ % b.value_;
        // Exact division -> the quotient's sign is a.neg XOR b.neg, no fixup.
        if (r == 0) {
            return from_parts(q, a.negative_ != b.negative_);
        }
        // Non-zero remainder. floor() only differs from truncation when the
        // operands have DIFFERENT signs -- that is exactly the case where the
        // exact quotient is positive but the floor must round DOWN.
        if (a.negative_ == b.negative_) {
            return from_parts(q, a.negative_);  // truncation is already exact
        }
        // floor(-7 / 2) = -4, not -3. The result rounds away from zero, so it
        // carries the DIVIDEND's sign (a), not the divisor's.
        return from_parts(q + 1, a.negative_);
    }

    [[nodiscard]] friend std::pair<Base60Int, Base60Int> divmod(const Base60Int& a,
                                                               const Base60Int& b) {
        return {a / b, a % b};
    }

    [[nodiscard]] friend Base60Int abs(const Base60Int& a) {
        return Base60Int::from_parts(a.value_, false);
    }

    /// Integer exponentiation. Square-and-multiply: O(log e).
    [[nodiscard]] friend Base60Int pow(const Base60Int& a, std::uint64_t e) {
        Base60Int r(1);
        Base60Int base = a;
        while (e) {
            if (e & 1) r = r * base;
            e >>= 1;
            if (e) base = base * base;
        }
        return r;
    }

    // -- comparison -------------------------------------------------------
    // Ordered by SIGNED value. This differs from Python base60_int, which has
    // no sign at all; compare magnitudes with to_uint64() if that is what you
    // want.
    [[nodiscard]] friend bool operator==(const Base60Int& a, const Base60Int& b) noexcept {
        return a.value_ == b.value_ && (a.negative_ == b.negative_ || a.value_ == 0);
    }

    [[nodiscard]] friend std::strong_ordering operator<=>(const Base60Int& a,
                                                          const Base60Int& b) noexcept {
        if (a == b) return std::strong_ordering::equal;
        const bool an = a.is_negative();
        const bool bn = b.is_negative();
        if (an != bn) {
            return an ? std::strong_ordering::less : std::strong_ordering::greater;
        }
        if (a.value_ != b.value_) {
            return a.value_ < b.value_ ? std::strong_ordering::less
                                        : std::strong_ordering::greater;
        }
        return std::strong_ordering::equal;
    }

    /// Absolute comparison, ignoring sign.
    [[nodiscard]] static int compare_abs(const Base60Int& a, const Base60Int& b) noexcept {
        if (a.value_ < b.value_) return -1;
        if (a.value_ > b.value_) return 1;
        return 0;
    }

    // -- circular arithmetic ----------------------------------------------
    /// Reduce the magnitude into [0, modulus). std::domain_error if zero.
    [[nodiscard]] Base60Int mod_ring(std::uint64_t modulus) const {
        if (modulus == 0) {
            throw std::domain_error("Base60Int::mod_ring: modulus must be positive");
        }
        return from_parts(value_ % modulus, negative_);
    }

private:
    static constexpr Base60Int from_parts(std::uint64_t mag, bool neg) noexcept {
        Base60Int r;
        r.value_ = mag;
        r.negative_ = neg && mag != 0;
        return r;
    }

    static std::uint64_t check_add(std::uint64_t a, std::uint64_t b) {
        if (a > std::numeric_limits<std::uint64_t>::max() - b) {
            throw OverflowError("Base60Int: addition overflows 64 bits");
        }
        return a + b;
    }

    std::uint64_t value_ = 0;
    bool negative_ = false;
};

// ---------------------------------------------------------------------------
// Free-function digit-level API (no object construction), matching the Python
// base60_int low-level helpers.
// ---------------------------------------------------------------------------

/// Add two Base-60 strings. Throws std::overflow_error on 64-bit overflow.
[[nodiscard]] inline std::string add_b60(std::string_view a, std::string_view b) {
    const Base60Int x = Base60Int::from_string(a);
    const Base60Int y = Base60Int::from_string(b);
    try {
        return (x + y).to_b60();
    } catch (const OverflowError& e) {
        throw std::overflow_error(e.what());
    }
}

/// Subtract b from a. Requires a >= b; otherwise std::domain_error.
[[nodiscard]] inline std::string sub_b60(std::string_view a, std::string_view b) {
    const Base60Int x = Base60Int::from_string(a);
    const Base60Int y = Base60Int::from_string(b);
    if (x < y) {
        throw std::domain_error("base60 subtract: a < b");
    }
    return (x - y).to_b60();
}

/// Multiply two Base-60 strings. Throws std::overflow_error on overflow.
[[nodiscard]] inline std::string mul_b60(std::string_view a, std::string_view b) {
    const Base60Int x = Base60Int::from_string(a);
    const Base60Int y = Base60Int::from_string(b);
    try {
        return (x * y).to_b60();
    } catch (const OverflowError& e) {
        throw std::overflow_error(e.what());
    }
}

/// Quotient and remainder. Throws std::domain_error on a zero divisor.
[[nodiscard]] inline std::pair<std::string, std::string> divmod_b60(std::string_view a,
                                                                    std::string_view b) {
    const auto [q, r] = divmod(Base60Int::from_string(a), Base60Int::from_string(b));
    return {q.to_b60(), r.to_b60()};
}

}  // namespace hexa60

#endif  // HEXA60_INT_HPP
