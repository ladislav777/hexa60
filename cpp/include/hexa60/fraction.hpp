// hexa60/fraction.hpp -- periodic sexagesimal fractions with cycle detection.
//
// C++20 port of base60_arithmetic.base60_fraction.
//
// The denominator is ITSELF a Base-60 number, which is the single most common
// source of confusion here:
//
//   fraction("1", "10") divides 1 by 60, NOT by decimal 10, because "10" is
//   1*60 + 0 in Base-60.
//
// Verified reference values (canonical hexa60 alphabet):
//   1/3 = 0.L   1/2 = 0.W   1/4 = 0.F   1/5 = 0.C
//   1/6 = 0.A   2/3 = 0.g   1/7 = 0.8aH (cycle 8,a,H)
//
// Termination: exact fractions end at a zero remainder; repeating ones are
// detected by a repeated remainder and cut there. Max precision defaults to
// 20 digits, matching the Python reference.

#ifndef HEXA60_FRACTION_HPP
#define HEXA60_FRACTION_HPP

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "hexa60/codec.hpp"
#include "hexa60/int.hpp"

namespace hexa60 {

/// Immutable periodic sexagesimal fraction.
class Base60Fraction {
public:
    /// Build from a rational N/D, where N and D are DECIMAL uint64 values.
    ///
    /// NOTE: unlike Base60Int::from_string, these arguments are decimal, not
    /// Base-60 text. Use from_b60() to pass Base-60 text.
    ///
    /// Throws std::domain_error when `den` is zero.
    [[nodiscard]] static Base60Fraction from_ratio(std::uint64_t num, std::uint64_t den,
                                                   std::size_t max_precision = 20) {
        if (den == 0) {
            throw std::domain_error("Base60Fraction: division by zero");
        }
        return compute(Base60Int(num), Base60Int(den), max_precision);
    }

    /// Build from a rational given as Base-60 text.
    [[nodiscard]] static Base60Fraction from_b60(std::string_view numerator,
                                                 std::string_view denominator,
                                                 std::size_t max_precision = 20) {
        return compute(Base60Int::from_string(numerator),
                       Base60Int::from_string(denominator), max_precision);
    }

    /// The rendered result, e.g. "0.8aH" or "3.W".
    [[nodiscard]] const std::string& str() const noexcept { return text_; }

    /// Number of fractional digits produced.
    [[nodiscard]] std::size_t precision() const noexcept { return precision_; }

    /// True when expansion stopped because a remainder repeated.
    [[nodiscard]] bool is_repeating() const noexcept { return repeating_; }

    /// Index at which the cycle begins, or precision() when exact.
    [[nodiscard]] std::size_t cycle_start() const noexcept { return cycle_start_; }

    /// Decimal approximation, for display and sanity checks.
    [[nodiscard]] long double to_decimal() const noexcept {
        long double acc = 0.0L;
        bool after_point = false;
        long double frac_scale = 1.0L / static_cast<long double>(BASE);
        for (const char c : text_) {
            if (c == '.') {
                after_point = true;
                continue;
            }
            const std::uint8_t d = digit_of(c);
            if (d == 0xFF) continue;
            if (!after_point) {
                acc = acc * static_cast<long double>(BASE) + d;
            } else {
                acc += static_cast<long double>(d) * frac_scale;
                frac_scale /= static_cast<long double>(BASE);
            }
        }
        return acc;
    }

private:
    /// Long division in Base-60 with remainder-set cycle detection.
    [[nodiscard]] static Base60Fraction compute(Base60Int num, Base60Int den,
                                                std::size_t max_precision) {
        if (den.is_zero()) {
            throw std::domain_error("Base60Fraction: division by zero");
        }
        Base60Fraction f;
        f.whole_ = num / den;
        Base60Int rem = num % den;

        std::string out = f.whole_.to_b60();
        if (rem.is_zero()) {
            f.text_ = std::move(out);
            f.precision_ = 0;
            f.repeating_ = false;
            f.cycle_start_ = 0;
            return f;
        }

        out += '.';

        // seen[i] is the remainder seen at digit position i. Seeing the same
        // remainder again means every digit from that point will recur, so we
        // stop rather than emit digits forever.
        //
        // NOTE: the remainder sequence is compared on its VALUE. Comparing
        // digit lists by length instead is a real bug -- [0, 0] is the value
        // 0 with length 2, which is how the original Python version produced
        // an infinite loop.
        std::vector<Base60Int> seen;
        seen.reserve(max_precision);

        while (!rem.is_zero() && f.precision_ < max_precision) {
            const auto it = std::find(seen.begin(), seen.end(), rem);
            if (it != seen.end()) {
                f.repeating_ = true;
                f.cycle_start_ = static_cast<std::size_t>(it - seen.begin());
                break;
            }
            seen.push_back(rem);

            // Shift one base-60 place: multiply the remainder by 60.
            rem = rem * Base60Int(std::uint64_t{BASE});

            // Count how many times the denominator fits, by repeated
            // subtraction. At most 59 iterations because rem < 60 * den.
            std::uint64_t digit = 0;
            while (rem >= den) {
                rem = rem - den;
                ++digit;
            }
            out += ALPHABET[digit];
            ++f.precision_;
        }

        f.text_ = std::move(out);
        return f;
    }

    Base60Int whole_{0};
    std::string text_;
    std::size_t precision_ = 0;
    bool repeating_ = false;
    std::size_t cycle_start_ = 0;
};

/// Convenience wrapper: decimal N / decimal D as Base-60 text.
[[nodiscard]] inline std::string fraction_b60(std::uint64_t num, std::uint64_t den,
                                              std::size_t max_precision = 20) {
    return Base60Fraction::from_ratio(num, den, max_precision).str();
}

}  // namespace hexa60

#endif  // HEXA60_FRACTION_HPP
