// hexa60/tensor.hpp -- fixed-width batch arithmetic on digit arrays.
//
// C++20 port of base60_tensor.py. No external dependencies: it works on plain
// std::array of digits, with no Eigen/OpenCL required.
//
// DIGIT ORDER -- this is the part that is easy to get wrong:
//
// Arrays here are MSB first (index 0 is the MOST significant digit), matching
// the Python reference. Schoolbook multiplication needs exponents to ADD, and
// the exponent of the digit at index i in a width-w array is (w-1-i). So:
//
//     (w-1-i) + (w-1-j) = 2*w-2-i-j
//
// which is the index into a width-(2w) accumulation buffer. Using i+j
// instead -- the LSB-first formula -- shifts every product and silently returns
// a wrong number. That was the original bug in the Python tensor.
//
// Carry then propagates from the LOWEST exponent to the highest, which is
// index 0 upward in this layout.

#ifndef HEXA60_TENSOR_HPP
#define HEXA60_TENSOR_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include "hexa60/codec.hpp"

namespace hexa60::tensor {

/// Row of `W` base-60 digits, MSB first.
template <std::size_t W>
using Row = std::array<std::uint8_t, W>;

/// A batch of rows.
template <std::size_t W>
using Batch = std::vector<Row<W>>;

/// Raised when a digit is out of range or a result does not fit the width.
class DigitError : public std::out_of_range {
public:
    explicit DigitError(const std::string& what) : std::out_of_range(what) {}
};

/// Validate one row: every digit must be in [0, BASE).
template <std::size_t W>
void validate(const Row<W>& r) {
    for (std::size_t i = 0; i < W; ++i) {
        if (r[i] >= BASE) {
            throw DigitError("base60 digit " + std::to_string(r[i]) + " at index " +
                             std::to_string(i) + " is out of range [0, " +
                             std::to_string(BASE) + ")");
        }
    }
}

/// Parse a canonical Base-60 string into a width-W MSB-first row.
/// Throws std::invalid_argument if the text is longer than W digits.
template <std::size_t W>
[[nodiscard]] Row<W> from_string(std::string_view s) {
    if (s.size() > W) {
        throw std::invalid_argument("base60_tensor: '" + std::string(s) + "' has " +
                                    std::to_string(s.size()) + " digits, max is " +
                                    std::to_string(W));
    }
    Row<W> r{};
    const std::size_t pad = W - s.size();
    for (std::size_t i = pad; i < W; ++i) {
        const std::uint8_t d = digit_of(s[i - pad]);
        if (d == 0xFF) {
            throw InvalidCharacterError(s[i - pad], i - pad);
        }
        r[i] = d;
    }
    return r;
}

/// Render a row as canonical Base-60 text with leading zeros stripped.
template <std::size_t W>
[[nodiscard]] std::string to_string(const Row<W>& r) {
    std::size_t start = 0;
    while (start + 1 < W && r[start] == 0) ++start;  // keep at least one digit
    std::string out;
    out.reserve(W - start);
    for (std::size_t i = start; i < W; ++i) {
        out += ALPHABET[r[i]];
    }
    return out;
}

/// a + b, digitwise with carry. Throws DigitError on overflow past width W.
template <std::size_t W>
[[nodiscard]] Row<W> add(const Row<W>& a, const Row<W>& b) {
    validate(a);
    validate(b);
    Row<W> out{};
    std::uint64_t carry = 0;
    // MSB first -> walk from the END (lowest exponent) toward the start.
    for (std::size_t k = W; k-- > 0;) {
        const std::uint64_t s = a[k] + b[k] + carry;
        out[k] = static_cast<std::uint8_t>(s % BASE);
        carry = s / BASE;
    }
    if (carry != 0) {
        throw DigitError("base60_tensor::add: result needs more than " +
                         std::to_string(W) + " digits");
    }
    return out;
}

/// a - b, digitwise with borrow. Throws DigitError if a < b.
template <std::size_t W>
[[nodiscard]] Row<W> subtract(const Row<W>& a, const Row<W>& b) {
    validate(a);
    validate(b);
    Row<W> out{};
    std::uint64_t borrow = 0;
    for (std::size_t k = W; k-- > 0;) {
        std::int64_t d = static_cast<std::int64_t>(a[k]) -
                         static_cast<std::int64_t>(b[k]) -
                         static_cast<std::int64_t>(borrow);
        if (d < 0) {
            d += static_cast<std::int64_t>(BASE);
            borrow = 1;
        } else {
            borrow = 0;
        }
        out[k] = static_cast<std::uint8_t>(d);
    }
    if (borrow != 0) {
        throw DigitError("base60_tensor::subtract: negative result");
    }
    return out;
}

/// a * b by schoolbook convolution. Throws DigitError if the product needs
/// more than W digits.
///
/// OVERFLOW ANALYSIS -- why uint64_t is safe, and where it stops being safe.
///
/// Each raw[k] accumulates the products a[i]*b[j] whose exponents sum to k.
/// Every such product is at most 59*59 = 3481, and at most W of them can land
/// on one slot (that happens at i=j=0), so BEFORE the carry pass:
///
///     raw[k] <= 3481 * W
///
/// The carry pass then computes s = raw[k] + carry, with the next carry
/// being s/60. Solving the geometric series gives a fixed point:
///
///     s_max = raw_max * 60/59  ~=  3540 * W
///
/// For uint64_t (2^64 - 1 = 1.845e19) that stays safe up to
/// W ~= 5.2e15 -- which is unreachable, since std::array<uint64_t, 2*W>
/// would need 80 PB of memory long before that.
///
/// So there is NO practical limit on W here, and an earlier comment claiming
/// W <= 31 was over-conservative and wrongly justified. The check below
/// encodes the ACTUAL bound so a future refactor cannot silently lose it.
/// If W ever became that large, use unsigned __int128 for the accumulator.
template <std::size_t W>
[[nodiscard]] Row<W> multiply(const Row<W>& a, const Row<W>& b) {
    validate(a);
    validate(b);

    // Compile-time overflow proof, derived above: 3481*W*60/59 must fit.
    constexpr std::size_t kPerProduct = 3481;  // 59 * 59
    constexpr std::size_t kCarryFactor = 60;   // s_max = raw_max * 60/59, rounded up
    constexpr bool kAccumulatorFits =
        kPerProduct > 0 && W <= (std::numeric_limits<std::uint64_t>::max() /
                                 kPerProduct) * 59 / kCarryFactor;
    static_assert(kAccumulatorFits || W == 0,
                  "Base60 tensor multiply: W is so large that the convolution "
                  "accumulator would overflow uint64_t. Use unsigned __int128.");

    // raw[k] accumulates products by EXPONENT k, so the buffer is 2W wide and
    // the result's low W digits live at raw[0..W-1].
    std::array<std::uint64_t, 2 * W> raw{};
    // Exponents add: digit a[i] has exponent (W-1-i), so a[i]*b[j] has
    // exponent 2W-2-i-j. Using i+j here (the LSB-first formula) shifts every
    // product and returns a wrong number.
    for (std::size_t i = 0; i < W; ++i) {
        for (std::size_t j = 0; j < W; ++j) {
            raw[2 * W - 2 - i - j] += static_cast<std::uint64_t>(a[i]) * b[j];
        }
    }
    // Carry from the lowest exponent (index 0) upward.
    std::uint64_t carry = 0;
    for (std::size_t k = 0; k < 2 * W; ++k) {
        const std::uint64_t s = raw[k] + carry;
        raw[k] = s % BASE;
        carry = s / BASE;
    }
    if (carry != 0) {
        throw DigitError("base60_tensor::multiply: result needs more than " +
                         std::to_string(W) + " digits");
    }
    for (std::size_t k = W; k < 2 * W; ++k) {
        if (raw[k] != 0) {
            throw DigitError("base60_tensor::multiply: result needs more than " +
                             std::to_string(W) + " digits");
        }
    }
    // raw[k] holds EXPONENT k (LSB first). The Row is MSB first, so the
    // low-W digits must be reversed on the way out: out[W-1-k] = raw[k].
    // Omitting this flip is the bug the Python tensor had -- it shifted the
    // whole product by (W-1) places.
    Row<W> out{};
    for (std::size_t k = 0; k < W; ++k) {
        out[W - 1 - k] = static_cast<std::uint8_t>(raw[k]);
    }
    return out;
}

/// Lexicographic compare of two MSB-first rows: -1, 0 or 1.
template <std::size_t W>
[[nodiscard]] int compare(const Row<W>& a, const Row<W>& b) noexcept {
    for (std::size_t i = 0; i < W; ++i) {
        if (a[i] != b[i]) return a[i] < b[i] ? -1 : 1;
    }
    return 0;
}

}  // namespace hexa60::tensor

#endif  // HEXA60_TENSOR_HPP
