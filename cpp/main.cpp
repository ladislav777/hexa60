// main.cpp -- end-to-end demonstration of the hexa60 C++20 library.
//
// Build (MSVC):
//   cl /std:c++20 /EHsc /W4 /I include main.cpp
// Build (GCC/Clang):
//   g++ -std=c++20 -Wall -Wextra -I include main.cpp -o demo

#include "hexa60.hpp"

#include <iostream>
#include <string>
#include <vector>

namespace {

void section(const char* title) {
    std::cout << "\n=== " << title << " ===\n";
}

std::string to_text(const std::vector<std::uint8_t>& v) {
    return std::string(v.begin(), v.end());
}

}  // namespace

int main() {
    using namespace hexa60;

    std::cout << "hexa60 v" << VERSION_MAJOR << "." << VERSION_MINOR << "."
              << VERSION_PATCH << " (C++20, header-only)\n";

    // ---------------------------------------------------------------- codec
    section("1. Codec: bytes <-> Base60 text");

    const std::string message = "Hello, HEXA60!";
    const std::string encoded = encode(message);
    std::cout << "  input    : \"" << message << "\"\n";
    std::cout << "  encoded  : " << encoded << "\n";
    std::cout << "  length   : " << message.size() << " bytes -> " << encoded.size()
              << " chars (ratio "
              << static_cast<double>(encoded.size()) / static_cast<double>(message.size())
              << ")\n";
    std::cout << "  decoded  : \"" << to_text(decode(encoded)) << "\"\n";

    // Leading zero bytes are preserved: the tail width carries the length.
    const std::string zeros = std::string("\x00\x00\x00\x00\x00", 5);
    std::cout << "  5 zero bytes -> " << encode(zeros) << " -> " << decode(encode(zeros)).size()
              << " bytes back\n";

    // Over-capacity chunks are rejected, never truncated.
    try {
        (void)decode(std::string(CHUNK_CHARS, '-'));  // 11 * 59 > 2^64
        std::cout << "  ERROR: over-capacity chunk was accepted\n";
    } catch (const LengthError& e) {
        std::cout << "  over-capacity chunk rejected: " << e.what() << "\n";
    }

    // -------------------------------------------------------- Base60Int
    section("2. Base60Int arithmetic");

    const Base60Int sixty(60);
    std::cout << "  60 in Base-60            : " << sixty.to_b60() << "\n";
    std::cout << "  60 + 60                 : " << (sixty + sixty).to_b60() << "\n";
    std::cout << "  60 * 60                 : " << (sixty * sixty).to_b60() << "\n";
    std::cout << "  2^10                    : " << pow(Base60Int(2), 10).to_b60() << "\n";
    const auto [q, r] = divmod(sixty, Base60Int(7));
    std::cout << "  60 divmod 7             : " << q.to_b60() << " remainder " << r.to_b60()
              << "\n";
    std::cout << "  modular ring 100 mod 60 : " << Base60Int(100).mod_ring(60).to_b60()
              << "\n";

    // The sign is opt-in, because '-' is ALPHABET[59] -- the digit 59.
    std::cout << "  ALPHABET[59]             : '" << ALPHABET[59] << "' (a digit, not a sign)\n";
    const Base60Int neg(-60);
    std::cout << "  -60 signed form         : " << neg.to_signed_string() << "\n";
    std::cout << "  parse \"-\" as a digit    : " << Base60Int::from_string("-").to_uint64()
              << "\n";

    // Floor vs truncating division.
    std::cout << "  floor(-7/2)              : " << div_floor(Base60Int(-7), Base60Int(2)).to_int64()
              << "  (truncating gives "
              << (Base60Int(-7) / Base60Int(2)).to_int64() << ")\n";

    // ------------------------------------------------------------ fraction
    section("3. Periodic fractions");

    std::cout << "  1/2 = " << fraction_b60(1, 2) << "\n";
    std::cout << "  1/3 = " << fraction_b60(1, 3) << "\n";
    std::cout << "  1/7 = " << fraction_b60(1, 7) << "   (cycle 8,a,H)\n";
    std::cout << "  7/2 = " << fraction_b60(7, 2) << "\n";

    // The denominator is itself Base-60 text in from_b60.
    std::cout << "  from_b60(\"1\", \"10\") = " << Base60Fraction::from_b60("1", "10").str()
              << "   (\"10\" is 60, not decimal 10)\n";

    const auto third = Base60Fraction::from_ratio(1, 3);
    std::cout << "  1/3 is repeating        : " << (third.is_repeating() ? "yes" : "no")
              << ", cycle starts at " << third.cycle_start() << "\n";

    // ------------------------------------------------------------- tensor
    section("4. Tensor (fixed-width digit rows)");

    namespace T = hexa60::tensor;
    constexpr std::size_t W = 8;
    const auto lhs = T::from_string<W>("9Rh");
    const auto rhs = T::from_string<W>("4");
    std::cout << "  9Rh * 4 = " << T::to_string(T::multiply(lhs, rhs)) << "\n";
    std::cout << "  10 + 10 = " << T::to_string(T::add(T::from_string<W>("10"),
                                                       T::from_string<W>("10"))) << "\n";

    std::cout << "\nDone.\n";
    return 0;
}
