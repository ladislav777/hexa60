// test_hexa60.cpp -- unit tests for the hexa60 C++20 library.
//
// Two ways to run:
//   1. With GoogleTest:  gtest/gtest_main.cc + this file
//   2. Without:          a minimal built-in harness is used automatically when
//                        HEXA60_NO_GTEST is defined, so the suite still runs on
//                        a machine with no external dependencies.
//
// Build with GoogleTest:
//   cl /std:c++20 /EHsc /I include /I <gtest-include> test_hexa60.cpp <gtest libs>
//
// Build standalone:
//   cl /std:c++20 /EHsc /DHEXA60_NO_GTEST /I include test_hexa60.cpp

#include "hexa60.hpp"

#include <cmath>
#include <string>
#include <vector>

// The library lives in namespace hexa60; the tests use it unqualified.
using namespace hexa60;

// ---------------------------------------------------------------------------
// Minimal harness, used when GoogleTest is unavailable.
// ---------------------------------------------------------------------------
#ifdef HEXA60_NO_GTEST

#include <cstdio>
#include <fstream>
#include <functional>
#include <string>
#include <vector>

namespace harness {

struct Case {
    std::string name;
    std::function<void()> fn;
};

std::vector<Case>& cases() {
    static std::vector<Case> c;
    return c;
}

int& failures() {
    static int f = 0;
    return f;
}

/// Number of EXPECT_* failures recorded, used to report per-test counts.
int& message_count() {
    static int m = 0;
    return m;
}

struct Registrar {
    Registrar(const char* name, std::function<void()> fn) {
        cases().push_back({name, std::move(fn)});
    }
};

void fail(const char* expr, const char* file, int line) {
    ++failures();
    ++message_count();
    std::printf("  FAIL %s:%d  %s\n", file, line, expr);
}

}  // namespace harness

#define TEST(name)                                                     \
    static void test_##name();                                         \
    static harness::Registrar reg_##name(#name, test_##name);          \
    static void test_##name()

#define EXPECT_TRUE(x)  do { if (!(x)) harness::fail(#x, __FILE__, __LINE__); } while (0)
#define EXPECT_FALSE(x) do { if ((x))  harness::fail("!" #x, __FILE__, __LINE__); } while (0)
#define EXPECT_EQ(a, b) do { if (!((a) == (b))) harness::fail(#a " == " #b, __FILE__, __LINE__); } while (0)
#define EXPECT_NE(a, b) do { if ((a) == (b))  harness::fail(#a " != " #b, __FILE__, __LINE__); } while (0)
#define EXPECT_LT(a, b) do { if (!((a) < (b))) harness::fail(#a " < " #b, __FILE__, __LINE__); } while (0)
#define EXPECT_GT(a, b) do { if (!((a) > (b))) harness::fail(#a " > " #b, __FILE__, __LINE__); } while (0)
#define EXPECT_THROW(stmt, ex)                                        \
    do {                                                              \
        bool thrown = false;                                          \
        try { (void)(stmt); } catch (const ex&) { thrown = true; }    \
        catch (...) {}                                                \
        if (!thrown) harness::fail(#stmt " should throw " #ex, __FILE__, __LINE__); \
    } while (0)
#define EXPECT_NO_THROW(stmt)                                         \
    do { try { (void)(stmt); } catch (...) { harness::fail(#stmt " threw", __FILE__, __LINE__); } } while (0)

#endif  // HEXA60_NO_GTEST

// ===========================================================================
// Alphabet and constants
// ===========================================================================
TEST(AlphabetHasSixtyDistinctCharacters) {
    EXPECT_EQ(ALPHABET_SIZE, std::size_t{60});
    EXPECT_EQ(BASE, std::size_t{60});
    for (std::size_t i = 0; i < ALPHABET_SIZE; ++i) {
        for (std::size_t j = i + 1; j < ALPHABET_SIZE; ++j) {
            EXPECT_TRUE(ALPHABET[i] != ALPHABET[j]);
        }
    }
}

TEST(AlphabetLookupIsInverse) {
    for (std::size_t i = 0; i < ALPHABET_SIZE; ++i) {
        EXPECT_EQ(static_cast<int>(digit_of(ALPHABET[i])), static_cast<int>(i));
        EXPECT_TRUE(is_alphabet_char(ALPHABET[i]));
    }
}

TEST(AlphabetIsUrlSafe) {
    // The whole point of the alphabet: no character that needs escaping.
    for (std::size_t i = 0; i < ALPHABET_SIZE; ++i) {
        const char c = ALPHABET[i];
        EXPECT_TRUE(c != '+');
        EXPECT_TRUE(c != '/');
        EXPECT_TRUE(c != '=');
        EXPECT_TRUE(c != '%');
        EXPECT_TRUE(c != '&');
        EXPECT_TRUE(c != '?');
        EXPECT_TRUE(c != ' ');
    }
}

TEST(AlphabetExcludesVisuallyAmbiguous) {
    // I, O, l, o are omitted to avoid 1/l and 0/O confusion.
    for (const char c : std::string("IOlo")) {
        EXPECT_FALSE(is_alphabet_char(c));
    }
}

TEST(LastAlphabetCharIsFiftyNine) {
    EXPECT_EQ(ALPHABET[59], '-');
    EXPECT_EQ(static_cast<int>(digit_of('-')), 59);
}

// ===========================================================================
// Tail table
// ===========================================================================
TEST(TailCharsMatchCapacityFormula) {
    // TAIL_CHARS[r] == ceil(r * 8 / log2(60))
    for (std::size_t r = 0; r < 8; ++r) {
        const double exact = r * 8.0 / std::log2(60.0);
        const std::size_t want = static_cast<std::size_t>(std::ceil(exact));
        EXPECT_EQ(TAIL_CHARS[r], want);
    }
}

TEST(TailCharsExactValues) {
    // Verified against ceil(r * 8 / log2(60)).
    const std::size_t expected[8] = {0, 2, 3, 5, 6, 7, 9, 10};
    for (std::size_t r = 0; r < 8; ++r) {
        EXPECT_EQ(TAIL_CHARS[r], expected[r]);
    }
}

TEST(TailResiduesAreUnique) {
    // The tail length must be recoverable from len(text) % 11.
    bool seen[CHUNK_CHARS + 1] = {};
    for (std::size_t r = 0; r < 8; ++r) {
        const std::size_t rem = TAIL_CHARS[r] % CHUNK_CHARS;
        EXPECT_FALSE(seen[rem]);
        seen[rem] = true;
    }
}

TEST(TailCapacityIsSufficientAndMinimal) {
    // For each r: 60^TAIL_CHARS[r] >= 2^(8r)   (it fits)
    //        and 60^(TAIL_CHARS[r]-1) < 2^(8r)  (it is not wasteful)
    const double log2base = 5.906890595608519;  // log2(60)
    for (std::size_t r = 1; r < 8; ++r) {
        const std::size_t c = TAIL_CHARS[r];
        const double bits_available = c * log2base;
        const double bits_needed = 8.0 * static_cast<double>(r);
        EXPECT_TRUE(bits_available >= bits_needed);
        if (c > 0) {
            EXPECT_TRUE((c - 1) * log2base < bits_needed);
        }
    }
}

TEST(TailCapacityOfFiveBytesNeedsSevenCharsNotEight) {
    // Regression: a spec that says TAIL_CHARS[5] == 8 is wrong. 60^6 = 2.18e10
    // < 2^40 (5 bytes), but 60^7 = 2.80e12 >= 2^40, so 7 is the minimum.
    EXPECT_EQ(TAIL_CHARS[5], std::size_t{7});
    EXPECT_TRUE(std::pow(60.0, 6.0) < std::pow(2.0, 40.0));
    EXPECT_TRUE(std::pow(60.0, 7.0) >= std::pow(2.0, 40.0));
}

// ===========================================================================
// Codec: roundtrip
// ===========================================================================
TEST(CodecEmptyInput) {
    EXPECT_EQ(encode(nullptr, 0), std::string(""));
    EXPECT_EQ(decode("").size(), std::size_t{0});
}

TEST(CodecRoundtripEveryLengthUpTo300) {
    for (std::size_t n = 0; n <= 300; ++n) {
        std::string in;
        for (std::size_t i = 0; i < n; ++i) {
            in += static_cast<char>((i * 37 + n) % 256);
        }
        const auto out = decode(encode(in));
        EXPECT_EQ(std::string(out.begin(), out.end()), in);
    }
}

TEST(CodecPreservesLeadingZeroBytes) {
    for (std::size_t n = 1; n <= 7; ++n) {
        const std::string zeros(n, '\0');
        const auto out = decode(encode(zeros));
        EXPECT_EQ(out.size(), n);
        for (const std::uint8_t b : out) EXPECT_EQ(int(b), 0);
    }
}

TEST(CodecPreservesAllByteValues) {
    std::string all;
    for (int i = 0; i < 256; ++i) all += static_cast<char>(i);
    const auto out = decode(encode(all));
    EXPECT_EQ(std::string(out.begin(), out.end()), all);
}

TEST(CodecChunkSizeIsElevenChars) {
    // 8 bytes -> exactly 11 chars.
    const std::string eight(8, 'a');
    EXPECT_EQ(encode(eight).size(), std::size_t{11});
    const std::string sixteen(16, 'a');
    EXPECT_EQ(encode(sixteen).size(), std::size_t{22});
}

TEST(CodecOutputUsesOnlyAlphabet) {
    const auto e = encode(std::string("identifier-safe? +/=&%# \n\t"));
    for (const char c : e) EXPECT_TRUE(is_alphabet_char(c));
}

// ===========================================================================
// Codec: strict validation
// ===========================================================================
TEST(CodecRejectsInvalidCharacter) {
    // A bad character inside a VALID length.
    EXPECT_THROW(decode("1!"), InvalidCharacterError);
    EXPECT_THROW(decode("+1"), InvalidCharacterError);   // '+' is not in the alphabet
    EXPECT_THROW(decode("1/1"), InvalidCharacterError);
    EXPECT_THROW(decode("1 1"), InvalidCharacterError);
    EXPECT_THROW(decode(std::string(11, '!')), InvalidCharacterError);
}

TEST(CodecLengthIsCheckedBeforeCharacters) {
    // "!" alone is 1 char, which is not a valid layout -- so this reports a
    // length problem, not a character problem. Length is validated first, which
    // is intentional: it is the cheaper check and the more useful error.
    EXPECT_THROW(decode("!"), LengthError);
    EXPECT_THROW(decode("+"), LengthError);
}

TEST(CodecInvalidCharacterCarriesPosition) {
    // "11!1" is 4 chars -> residue 4, which is NOT a valid tail, so the
    // length check fires before the character check. Use a valid layout
    // instead: 11 chars is one full chunk, and the '!' is at index 2.
    try {
        (void)decode("11!11111111");
        EXPECT_TRUE(false);  // should have thrown
    } catch (const InvalidCharacterError& e) {
        EXPECT_EQ(e.position(), std::size_t{2});
        EXPECT_EQ(e.character(), '!');
    }
}

TEST(CodecPositionIsAbsoluteAcrossChunks) {
    // The bad character sits in the SECOND chunk, so the reported position must
    // be absolute -- its index in the whole string -- not relative to the chunk.
    //
    // 22 chars = 2 full chunks of 11, a valid layout. The '!' is at index 15,
    // which is offset 4 within the second chunk.
    const std::string s = "111111111111111!111111";
    EXPECT_EQ(s.size(), std::size_t{22});
    EXPECT_EQ(s[15], '!');
    try {
        (void)decode(s);
        EXPECT_TRUE(false);
    } catch (const InvalidCharacterError& e) {
        EXPECT_EQ(e.position(), std::size_t{15});
    }
}

TEST(CodecRejectsInvalidLengths) {
    // Valid residues mod 11 are 0, 2, 3, 5, 6, 7, 9, 10.  So 1, 4 and 8 are
    // the invalid ones, plus anything congruent to them.
    for (const std::size_t bad : {std::size_t{1}, std::size_t{4}, std::size_t{8},
                                  std::size_t{12}, std::size_t{15}, std::size_t{19}}) {
        EXPECT_THROW(decode(std::string(bad, '1')), LengthError);
    }
    // Every valid residue must be accepted. NOTE: 6 is VALID (a 4-byte tail),
    // not invalid -- the tail table has {0,2,3,5,6,7,9,10} chars.
    for (const std::size_t good : {std::size_t{0}, std::size_t{2}, std::size_t{3},
                                   std::size_t{5}, std::size_t{6}, std::size_t{7},
                                   std::size_t{9}, std::size_t{10}, std::size_t{11}}) {
        EXPECT_NO_THROW((void)decode(std::string(good, '0')));
    }
}

TEST(CodecRejectsOverCapacityChunk) {
    // 60^11 > 2^64, so an 11-char block of all '-' (59) does not fit in 8 bytes.
    // It must be REJECTED, never silently truncated.
    EXPECT_THROW(decode(std::string(11, '-')), LengthError);
    EXPECT_THROW(decode(std::string(22, '-')), LengthError);
}

TEST(CodecAcceptsMaximumChunk) {
    // 8 bytes of 0xFF must roundtrip.
    const std::string maxbytes(8, '\xff');
    EXPECT_NO_THROW((void)decode(encode(maxbytes)));
}

TEST(CodecRejectsOverCapacityTail) {
    // A 2-char tail holding 59*60+59 = 3599 does not fit in 1 byte.
    EXPECT_THROW(decode("-_"), LengthError);
}

TEST(IsValidHelpers) {
    EXPECT_TRUE(is_valid(""));
    EXPECT_TRUE(is_valid("abcXYZ_-019"));
    EXPECT_FALSE(is_valid("abc!"));
    EXPECT_FALSE(is_valid("IOlo"));  // not in the alphabet
    EXPECT_TRUE(is_valid_length(0));
    EXPECT_TRUE(is_valid_length(11));
    EXPECT_TRUE(is_valid_length(2));
    EXPECT_TRUE(is_valid_length(3));
    EXPECT_FALSE(is_valid_length(1));
    EXPECT_FALSE(is_valid_length(4));
}

// ===========================================================================
// Base60Int
// ===========================================================================
TEST(IntRoundtrip) {
    for (const std::uint64_t v : {0ULL, 1ULL, 59ULL, 60ULL, 3599ULL, 3600ULL,
                                   12345ULL, 1000000007ULL}) {
        EXPECT_EQ(Base60Int::from_string(Base60Int(v).to_b60()).to_uint64(), v);
    }
}

TEST(IntCanonicalFormatting) {
    EXPECT_EQ(Base60Int(std::uint64_t{0}).to_b60(), std::string("0"));
    EXPECT_EQ(Base60Int(std::uint64_t{1}).to_b60(), std::string("1"));
    EXPECT_EQ(Base60Int(std::uint64_t{59}).to_b60(), std::string("-"));
    EXPECT_EQ(Base60Int(std::uint64_t{60}).to_b60(), std::string("10"));
    EXPECT_EQ(Base60Int(std::uint64_t{3600}).to_b60(), std::string("100"));
    // leading zeros are stripped
    EXPECT_EQ(Base60Int::from_string("000123").to_b60(), std::string("123"));
}

TEST(IntStripsLeadingZeros) {
    EXPECT_EQ(Base60Int::from_string("000").to_b60(), std::string("0"));
    EXPECT_EQ(Base60Int::from_string("0000z").to_b60(), std::string("z"));
}

TEST(IntAddition) {
    EXPECT_EQ(add_b60("1", "1"), std::string("2"));
    EXPECT_EQ(add_b60("10", "10"), std::string("20"));
    // ALPHABET[59] is '-', so 59 + 1 carries into a new digit.
    EXPECT_EQ(add_b60("-", "1"), std::string("10"));
    // ALPHABET[58] is '_', so 58 + 1 is just 59.
    EXPECT_EQ(add_b60("_", "1"), std::string("-"));
}

TEST(IntSubtraction) {
    // 60 - 1 = 59 = '-'
    EXPECT_EQ(sub_b60("10", "1"), std::string("-"));
    // 3600 - 1 = 3599 = 59*60 + 59 = "--"
    EXPECT_EQ(sub_b60("100", "1"), std::string("--"));
    EXPECT_THROW(sub_b60("0", "1"), std::domain_error);
    EXPECT_THROW(sub_b60("1", "10"), std::domain_error);
}

TEST(IntMultiplication) {
    EXPECT_EQ(mul_b60("1", "1"), std::string("1"));
    EXPECT_EQ(mul_b60("0", "z"), std::string("0"));
    EXPECT_EQ(mul_b60("10", "10"), std::string("100"));
    // "12" is 62; 62*62 = 3844 = "144" in base 60
    EXPECT_EQ(mul_b60("12", "12"), std::string("144"));
}

TEST(IntDivisionAndModulo) {
    const auto [q, r] = divmod_b60("10", "3");  // 60 / 3 = 20, remainder 0
    EXPECT_EQ(q, std::string("L"));
    EXPECT_EQ(r, std::string("0"));
    EXPECT_THROW(divmod_b60("1", "0"), std::domain_error);
    EXPECT_THROW((void)(Base60Int(5) % Base60Int(0)), std::domain_error);
}

TEST(IntPower) {
    EXPECT_EQ(pow(Base60Int(2), 10).to_uint64(), 1024ULL);
    EXPECT_EQ(pow(Base60Int(2), 0).to_uint64(), 1ULL);
}

TEST(IntComparison) {
    EXPECT_TRUE(Base60Int(1) < Base60Int(2));
    EXPECT_TRUE(Base60Int(2) > Base60Int(1));
    EXPECT_TRUE(Base60Int(1) == Base60Int(1));
    EXPECT_TRUE(Base60Int(1) <= Base60Int(1));
    EXPECT_TRUE(Base60Int(2) >= Base60Int(2));
    EXPECT_TRUE(Base60Int(1) != Base60Int(2));
}

TEST(IntParseRejectsBadInput) {
    EXPECT_THROW(Base60Int::from_string(""), std::invalid_argument);
    EXPECT_THROW(Base60Int::from_string("!"), InvalidCharacterError);
    EXPECT_THROW(Base60Int::from_string("1!"), InvalidCharacterError);
    EXPECT_THROW(Base60Int::from_string("+"), InvalidCharacterError);
}

TEST(IntParseRejectsOverflow) {
    // 11 chars of 59 = 3.6e19 > 2^64
    EXPECT_THROW(Base60Int::from_string(std::string(11, '-')), OverflowError);
}

TEST(IntOverflowIsNeverSilent) {
    EXPECT_THROW(pow(Base60Int(0xFFFFFFFFFFFFULL), 4), OverflowError);
}

// ---- the sign question ----------------------------------------------------
TEST(DashIsADigitNotASign) {
    // '-' is ALPHABET[59]. Parsing it WITHOUT opt-in must give 59, not a
    // negative number. This is the ambiguity the API splits on.
    EXPECT_EQ(Base60Int::from_string("-").to_uint64(), 59ULL);
    EXPECT_FALSE(Base60Int::from_string("-").is_negative());
}

TEST(SignedParsingIsOptIn) {
    const auto n = Base60Int::from_string_signed("-10");
    EXPECT_TRUE(n.is_negative());
    EXPECT_EQ(n.to_int64(), -60);
    EXPECT_EQ(n.to_signed_string(), std::string("-10"));
    // to_b60() is always the unsigned wire form
    EXPECT_EQ(n.to_b60(), std::string("10"));
}

TEST(SignedArithmetic) {
    // NOTE: the Python reference has no sign at all (it raises ValueError).
    // The C++ port adds it as an opt-in, so these are C++-only expectations.
    const Base60Int neg10(std::int64_t{-10});
    const Base60Int pos10(std::int64_t{10});
    EXPECT_TRUE(neg10.is_negative());
    EXPECT_FALSE(pos10.is_negative());
    EXPECT_TRUE(neg10 < pos10);
    EXPECT_EQ((neg10 + pos10).to_int64(), 0);
    EXPECT_EQ((neg10 + neg10).to_int64(), -20);
    EXPECT_EQ((neg10 * pos10).to_int64(), -100);
    EXPECT_EQ(abs(neg10).to_int64(), 10);
    EXPECT_FALSE(abs(neg10).is_negative());
    // subtraction crosses zero correctly
    EXPECT_EQ((pos10 - neg10).to_int64(), 20);
    EXPECT_EQ((neg10 - pos10).to_int64(), -20);
}

TEST(FloorDivisionDiffersFromTruncating) {
    const Base60Int n7(std::int64_t{-7});
    const Base60Int n2(std::int64_t{2});
    // C++ truncation: -7/2 == -3.  floor(): -4.
    EXPECT_EQ((n7 / n2).to_int64(), -3);
    EXPECT_EQ(div_floor(n7, n2).to_int64(), -4);
    // exact cases agree
    EXPECT_EQ(div_floor(n7, Base60Int(1)).to_int64(), -7);
    EXPECT_EQ(div_floor(Base60Int(4), n2).to_int64(), 2);
}

TEST(ZeroHasNoNegativeSign) {
    EXPECT_FALSE(Base60Int(0).is_negative());
    EXPECT_TRUE(Base60Int(0).is_zero());
    EXPECT_EQ(Base60Int(std::int64_t{0}).to_signed_string(), std::string("0"));
}

TEST(FromBytesAndToInt) {
    const std::uint8_t buf[2] = {0x01, 0x00};
    EXPECT_EQ(Base60Int::from_bytes(buf, 2).to_uint64(), 256ULL);
    EXPECT_EQ(Base60Int::from_bytes(nullptr, 0).to_uint64(), 0ULL);
}

// ===========================================================================
// Base60Fraction
// ===========================================================================
TEST(FractionKnownValues) {
    // Verified against the Python reference (base60_arithmetic).
    EXPECT_EQ(Base60Fraction::from_ratio(1, 3).str(), std::string("0.L"));
    EXPECT_EQ(Base60Fraction::from_ratio(1, 2).str(), std::string("0.W"));
    EXPECT_EQ(Base60Fraction::from_ratio(1, 4).str(), std::string("0.F"));
    EXPECT_EQ(Base60Fraction::from_ratio(1, 5).str(), std::string("0.C"));
    EXPECT_EQ(Base60Fraction::from_ratio(1, 6).str(), std::string("0.A"));
    EXPECT_EQ(Base60Fraction::from_ratio(2, 3).str(), std::string("0.g"));
    EXPECT_EQ(Base60Fraction::from_ratio(1, 7).str(), std::string("0.8aH"));
    EXPECT_EQ(Base60Fraction::from_ratio(7, 2).str(), std::string("3.W"));
}

TEST(FractionExactIntegers) {
    EXPECT_EQ(Base60Fraction::from_ratio(1, 1).str(), std::string("1"));
    EXPECT_EQ(Base60Fraction::from_ratio(2, 1).str(), std::string("2"));
    EXPECT_EQ(Base60Fraction::from_ratio(60, 1).str(), std::string("10"));
    const auto f = Base60Fraction::from_ratio(2, 1);
    EXPECT_FALSE(f.is_repeating());
    EXPECT_EQ(f.precision(), std::size_t{0});
}

TEST(FractionTerminatesExactly) {
    // A repeating implementation would pad these with trailing zeros.
    // Verified against the Python reference:
    //   1/2 = 0.W  (1 digit, exact)
    //   1/4 = 0.F  (1 digit, exact -- 15/60 = 0.25)
    //   1/8 = 0.7W (3 digits, exact)
    const auto half = Base60Fraction::from_ratio(1, 2);
    EXPECT_EQ(half.str(), std::string("0.W"));
    EXPECT_EQ(half.precision(), std::size_t{1});
    EXPECT_FALSE(half.is_repeating());

    const auto quarter = Base60Fraction::from_ratio(1, 4);
    EXPECT_EQ(quarter.str(), std::string("0.F"));
    EXPECT_EQ(quarter.precision(), std::size_t{1});
    EXPECT_FALSE(quarter.is_repeating());

    // 1/8 = 0.875 = 7/60 + 30/3600 + 0/216000. The third digit is a genuine
    // zero, so it must be present.
    const auto eighth = Base60Fraction::from_ratio(1, 8);
    EXPECT_EQ(eighth.str(), std::string("0.7W"));
    EXPECT_EQ(eighth.precision(), std::size_t{2});
    EXPECT_FALSE(eighth.is_repeating());
}

TEST(FractionDetectsCycle) {
    const auto f = Base60Fraction::from_ratio(1, 7);
    EXPECT_TRUE(f.is_repeating());
    EXPECT_EQ(f.cycle_start(), std::size_t{0});
    EXPECT_EQ(f.precision(), std::size_t{3});
}

TEST(FractionDenominatorIsBase60Text) {
    // from_b60 takes Base-60 text. "10" is 60, so 1/"10" == 1/60 == 0.1.
    EXPECT_EQ(Base60Fraction::from_b60("1", "10").str(), std::string("0.1"));
    // "60" in Base-60 is 6*60 = 360, so 1/"60" == 1/360 == 0.0A
    EXPECT_EQ(Base60Fraction::from_b60("1", "60").str(), std::string("0.0A"));
    // "7" is the same in both, so this matches from_ratio(1, 7)
    EXPECT_EQ(Base60Fraction::from_b60("1", "7").str(),
              Base60Fraction::from_ratio(1, 7).str());
}

TEST(FractionRejectsZeroDenominator) {
    EXPECT_THROW(Base60Fraction::from_ratio(1, 0), std::domain_error);
    EXPECT_THROW(Base60Fraction::from_b60("1", "0"), std::domain_error);
}

TEST(FractionDecimalApproximation) {
    const auto third = Base60Fraction::from_ratio(1, 3).to_decimal();
    EXPECT_TRUE(std::fabs(third - 1.0 / 3.0) < 1e-6);
    const auto half = Base60Fraction::from_ratio(1, 2).to_decimal();
    EXPECT_TRUE(std::fabs(half - 0.5) < 1e-9);
    const auto two = Base60Fraction::from_ratio(2, 1).to_decimal();
    EXPECT_TRUE(std::fabs(two - 2.0) < 1e-9);
}

TEST(FractionMatchesDoubleForManyCases) {
    // Three error sources, in order of size:
    //
    //  1. SEXAGESIMAL TRUNCATION. An exact fraction stops at a zero
    //     remainder, so its expansion is a finite truncation: error < 60^-p.
    //     A repeating one stops when a remainder repeats, omitting at most
    //     one period: error < 60^-p as well.
    //
    //  2. FLOATING POINT. to_decimal() accumulates in long double, but the
    //     comparison here is in double, whose epsilon is ~2.2e-16. For a
    //     20-digit expansion the truncation error is ~1e-36, so double
    //     rounding DOMINATES and no truncation-based tolerance can work.
    //
    //  3. Converting the exact ratio n/d to double.
    //
    // So the tolerance must include a few multiples of DBL_EPSILON. Anything
    // tighter would be testing the FPU, not the fraction code.
    constexpr double kEps = 2.3e-16;
    for (std::uint64_t d = 2; d <= 40; ++d) {
        for (std::uint64_t n : {1ULL, 2ULL, 3ULL, 7ULL}) {
            if (n >= d) continue;
            const auto f = Base60Fraction::from_ratio(n, d);
            const double approx = static_cast<double>(f.to_decimal());
            const double want = static_cast<double>(n) / static_cast<double>(d);
            const double unit =
                f.precision() == 0
                    ? 0.0
                    : std::pow(60.0, -static_cast<double>(f.precision()));
            EXPECT_TRUE(std::fabs(approx - want) <= unit + 8.0 * kEps);
        }
    }
}

TEST(FractionTruncationErrorIsBoundedForShortExpansions) {
    // Where truncation genuinely dominates, the 60^-p bound must hold. That
    // needs a SHORT expansion, e.g. 1/7 with only 3 digits.
    const auto f = Base60Fraction::from_ratio(1, 7);
    EXPECT_EQ(f.precision(), std::size_t{3});
    const double approx = static_cast<double>(f.to_decimal());
    const double want = 1.0 / 7.0;
    const double err = std::fabs(approx - want);
    // Below 60^-3, and far above float noise.
    EXPECT_TRUE(err < std::pow(60.0, -3.0));
    EXPECT_TRUE(err > 1e-9);
}

TEST(FractionRepeatingErrorIsBoundedByOnePeriod) {
    // 1/7 = 0.8aH repeating. The 3-digit prefix 0.142856 is short by one
    // period, so the error is around 1.4e-6 -- well under 1/1000.
    const auto f = Base60Fraction::from_ratio(1, 7);
    EXPECT_TRUE(f.is_repeating());
    EXPECT_EQ(f.precision(), std::size_t{3});
    const double approx = static_cast<double>(f.to_decimal());
    EXPECT_TRUE(std::fabs(approx - 1.0 / 7.0) < 1.0 / 1000.0);
}

TEST(FractionThreeIsExactNotRepeating) {
    // 20/60 == 1/3 exactly, so the remainder hits zero after one digit and no
    // cycle is ever detected. This is the subtle case: the expansion LOOKS
    // periodic, but that single digit already IS the exact value.
    const auto f = Base60Fraction::from_ratio(1, 3);
    EXPECT_EQ(f.str(), std::string("0.L"));
    EXPECT_FALSE(f.is_repeating());
    EXPECT_EQ(f.precision(), std::size_t{1});
}

// ===========================================================================
// Tensor
// ===========================================================================
namespace T = hexa60::tensor;
constexpr std::size_t W = 8;

TEST(TensorRoundtripThroughStrings) {
    EXPECT_EQ(T::to_string(T::from_string<W>("9Rh")), std::string("9Rh"));
    EXPECT_EQ(T::to_string(T::from_string<W>("0")), std::string("0"));
    EXPECT_EQ(T::to_string(T::from_string<W>("0001")), std::string("1"));
}

TEST(TensorMultiplySmallExhaustive) {
    // All single-digit pairs: the product must equal the decimal product
    // re-encoded in base 60.
    for (int a = 0; a < 20; ++a) {
        for (int b = 0; b < 20; ++b) {
            const std::string sa(1, ALPHABET[a]);
            const std::string sb(1, ALPHABET[b]);
            const std::string got =
                T::to_string(T::multiply(T::from_string<W>(sa), T::from_string<W>(sb)));
            const std::uint64_t product = static_cast<std::uint64_t>(a * b);
            EXPECT_EQ(got, Base60Int(product).to_b60());
        }
    }
}

TEST(TensorMultiplyKnownValues) {
    EXPECT_EQ(T::to_string(T::multiply(T::from_string<W>("9Rh"), T::from_string<W>("4"))),
              std::string("dik"));
    EXPECT_EQ(T::to_string(T::multiply(T::from_string<W>("1"), T::from_string<W>("1"))),
              std::string("1"));
    EXPECT_EQ(T::to_string(T::multiply(T::from_string<W>("0"), T::from_string<W>("zzz"))),
              std::string("0"));
    EXPECT_EQ(T::to_string(T::multiply(T::from_string<W>("10"), T::from_string<W>("10"))),
              std::string("100"));
    // "12" is 62; 62*62 = 3844 = "144" in base 60
    EXPECT_EQ(T::to_string(T::multiply(T::from_string<W>("12"), T::from_string<W>("12"))),
              std::string("144"));
}

TEST(TensorMultiplyMatchesBase60Int) {
    // Deterministic cross-check. This is the test that catches an LSB/MSB
    // misalignment in the convolution.
    std::uint64_t seed = 12345;
    auto next_digit = [&seed]() {
        seed = seed * 6364136223846793005ULL + 1442695040888963407ULL;
        return static_cast<std::uint8_t>((seed >> 33) % 60);
    };
    int checked = 0;
    for (int t = 0; t < 3000; ++t) {
        std::string sa, sb;
        for (int i = 0; i < 4; ++i) sa += ALPHABET[next_digit()];
        for (int i = 0; i < 3; ++i) sb += ALPHABET[next_digit()];
        if (sa[0] == '0') sa[0] = '1';
        if (sb[0] == '0') sb[0] = '1';
        const Base60Int x = Base60Int::from_string(sa);
        const Base60Int y = Base60Int::from_string(sb);
        const std::string want = (x * y).to_b60();
        const bool fits = want.size() <= W;
        try {
            const std::string got = T::to_string(
                T::multiply(T::from_string<W>(sa), T::from_string<W>(sb)));
            if (fits) EXPECT_EQ(got, want);
        } catch (const T::DigitError&) {
            EXPECT_FALSE(fits);  // may only throw when it really overflows
        } catch (const OverflowError&) {
            EXPECT_FALSE(fits);
        }
        ++checked;
    }
    EXPECT_EQ(checked, 3000);
}

TEST(TensorAddAndSubtract) {
    EXPECT_EQ(T::to_string(T::add(T::from_string<W>("W"), T::from_string<W>("W"))),
              std::string("10"));
    EXPECT_EQ(T::to_string(T::add(T::from_string<W>("1"), T::from_string<W>("1"))),
              std::string("2"));
    // 60 - 1 = 59, and ALPHABET[59] is '-'
    EXPECT_EQ(T::to_string(T::subtract(T::from_string<W>("10"), T::from_string<W>("1"))),
              std::string("-"));
    EXPECT_EQ(T::to_string(T::subtract(T::from_string<W>("10"), T::from_string<W>("10"))),
              std::string("0"));
}

TEST(TensorAddMatchesBase60Int) {
    std::uint64_t seed = 999;
    auto next_digit = [&seed]() {
        seed = seed * 6364136223846793005ULL + 1442695040888963407ULL;
        return static_cast<std::uint8_t>((seed >> 33) % 60);
    };
    for (int t = 0; t < 2000; ++t) {
        std::string sa, sb;
        for (int i = 0; i < 3; ++i) sa += ALPHABET[next_digit()];
        for (int i = 0; i < 2; ++i) sb += ALPHABET[next_digit()];
        if (sa[0] == '0') sa[0] = '1';
        if (sb[0] == '0') sb[0] = '1';
        const std::string want =
            (Base60Int::from_string(sa) + Base60Int::from_string(sb)).to_b60();
        const bool fits = want.size() <= W;
        try {
            const std::string got =
                T::to_string(T::add(T::from_string<W>(sa), T::from_string<W>(sb)));
            if (fits) EXPECT_EQ(got, want);
        } catch (const T::DigitError&) {
            EXPECT_FALSE(fits);
        }
    }
}

/// N copies of `ch`. Helper so tests never hard-code the max digit.
std::string repeat(char ch, std::size_t n) {
    return std::string(n, ch);
}

TEST(TensorRejectsOverflow) {
    // The maximum W-digit value is 60^W - 1, i.e. W copies of the LAST
    // alphabet character. Do NOT hard-code it: ALPHABET[59] is '-', while 'z'
    // is only ALPHABET[57]. Read it from the table.
    const char max_digit = ALPHABET[BASE - 1];
    const auto max8 = T::from_string<W>(repeat(max_digit, 8));
    // (60^8 - 1)^2 has 16 digits, so it cannot fit in 8.
    EXPECT_THROW(T::multiply(max8, max8), T::DigitError);
    // Adding 1 to the maximum carries out of the width.
    EXPECT_THROW(T::add(max8, T::from_string<W>("1")), T::DigitError);

    // 2 * (60^7 - 1) = 2*60^7 - 2.  Since 2*60^7 < 60^8, this FITS in 8 digits.
    // Compute the magnitude as uint64_t -- a plain `60 * 60 * ...` literal chain
    // would be int arithmetic and overflow at compile time.
    std::uint64_t mag = 1;
    for (int i = 0; i < 7; ++i) mag *= std::uint64_t{60};
    const std::uint64_t twice = 2 * (mag - 1);
    const auto max7 = T::from_string<W>(repeat(max_digit, 7));
    EXPECT_NO_THROW((void)T::add(max7, max7));
    EXPECT_EQ(T::to_string(T::add(max7, max7)), Base60Int(twice).to_b60());
}

TEST(TensorRejectsNegativeSubtraction) {
    EXPECT_THROW(T::subtract(T::from_string<W>("1"), T::from_string<W>("10")),
                 T::DigitError);
}

TEST(TensorRejectsBadInput) {
    EXPECT_THROW(T::from_string<4>("12345"), std::invalid_argument);
    EXPECT_THROW(T::from_string<8>("1!"), InvalidCharacterError);
}

TEST(TensorCompare) {
    EXPECT_EQ(T::compare(T::from_string<W>("1"), T::from_string<W>("2")), -1);
    EXPECT_EQ(T::compare(T::from_string<W>("2"), T::from_string<W>("1")), 1);
    EXPECT_EQ(T::compare(T::from_string<W>("1"), T::from_string<W>("1")), 0);
    // compare works on the padded arrays, so 1 == 0001
    EXPECT_EQ(T::compare(T::from_string<W>("1"), T::from_string<W>("0001")), 0);
    // "10" is 60, so 10 > 2
    EXPECT_EQ(T::compare(T::from_string<W>("10"), T::from_string<W>("2")), 1);
}

// ===========================================================================
// Accumulator width: the multiply overflow proof must hold for real widths
// ===========================================================================
TEST(TensorMultiplyAtWidth64) {
    constexpr std::size_t Big = 64;
    // 60^3 - 1 = 215999, still exactly 3 digits
    const auto a = T::from_string<Big>("zzz");
    EXPECT_EQ(T::to_string(T::multiply(a, T::from_string<Big>("1"))), std::string("zzz"));
}

TEST(TensorMultiplyAtWidth128) {
    constexpr std::size_t Big = 128;
    const auto a = T::from_string<Big>(repeat(ALPHABET[BASE - 1], 4));
    // (60^4 - 1)^2 needs 8 digits, which fits comfortably in 128.
    std::uint64_t mag = 1;
    for (int i = 0; i < 4; ++i) mag *= std::uint64_t{60};
    const std::uint64_t p = (mag - 1) * (mag - 1);
    EXPECT_EQ(T::to_string(T::multiply(a, a)), Base60Int(p).to_b60());
}

TEST(TensorMultiplyAtWidth256TimesOne) {
    constexpr std::size_t Big = 256;
    // 200 digits: exercises the accumulator and the full 2W carry sweep.
    // The reference CANNOT be Base60Int -- a 200-digit value does not fit in
    // uint64_t, and Base60Int is deliberately 64-bit bounded. Verify the
    // identity x*1 == x against the CANONICAL form of the input.
    std::string s;
    for (int i = 0; i < 200; ++i) s += ALPHABET[(i * 13) % 60];
    std::string canon = s;
    const auto nz = canon.find_first_not_of('0');
    canon = (nz == std::string::npos) ? std::string("0") : canon.substr(nz);
    const auto a = T::from_string<Big>(s);
    EXPECT_EQ(T::to_string(T::multiply(a, T::from_string<Big>("1"))), canon);
}

TEST(TensorMultiplyRejectsOverflowAtLargeWidth) {
    // A genuine overflow must still be DETECTED at a wide width, never
    // silently truncated. (60^40 - 1)^2 needs 80 digits, more than the 64
    // the row can hold.
    constexpr std::size_t Big = 64;
    const auto a = T::from_string<Big>(repeat(ALPHABET[BASE - 1], 40));
    EXPECT_THROW(T::multiply(a, a), T::DigitError);
}

// ===========================================================================
// Cross-module consistency
// ===========================================================================
TEST(CrossModuleCodecAndIntAgree) {
    for (std::uint64_t mag : {0ULL, 1ULL, 255ULL, 256ULL, 65535ULL, 16777215ULL}) {
        const std::uint8_t buf[4] = {
            static_cast<std::uint8_t>(mag >> 24), static_cast<std::uint8_t>(mag >> 16),
            static_cast<std::uint8_t>(mag >> 8), static_cast<std::uint8_t>(mag)};
        EXPECT_EQ(Base60Int::from_bytes(buf, 4).to_uint64(), mag);
        const auto text = encode(buf, 4);
        const auto back = decode(text);
        EXPECT_EQ(back.size(), std::size_t{4});
        EXPECT_EQ(Base60Int::from_bytes(back.data(), back.size()).to_uint64(), mag);
    }
}

TEST(CrossModuleTensorMatchesInt) {
    const std::string tensor_out =
        T::to_string(T::multiply(T::from_string<W>("9Rh"), T::from_string<W>("4")));
    const std::string int_out =
        (Base60Int::from_string("9Rh") * Base60Int::from_string("4")).to_b60();
    EXPECT_EQ(tensor_out, int_out);
}

// ===========================================================================
// Entry point
// ===========================================================================
int main(int argc, char** argv) {
#ifdef HEXA60_NO_GTEST
    // Report location: argv[1] if given, else "./_tests_report.txt".
    //
    // This used to be a hard-coded absolute path ("C:/BASE60/cpp/..."), which
    // was wrong: running the suite from a fresh clone wrote the report back
    // into the developer's original checkout instead of next to the clone.
    // argv is used rather than getenv because MSVC warns C4996 for it at /W4.
    const std::string report =
        (argc > 1) ? std::string(argv[1]) : std::string("_tests_report.txt");
    std::ofstream out(report, std::ios::out | std::ios::trunc);
    if (!out) return 99;
    int run = 0;
    for (const auto& c : harness::cases()) {
        ++run;
        const int before = harness::failures();
        const int before_msg = harness::message_count();
        // An UNEXPECTED exception escaping a test would abort the whole run
        // and leave no report at all. Catch it and attribute it to the test.
        try {
            c.fn();
        } catch (const std::exception& e) {
            ++harness::failures();
            ++harness::message_count();
            out << "[FAIL] " << c.name << " threw: " << e.what() << "\n";
            out.flush();
            continue;
        } catch (...) {
            ++harness::failures();
            ++harness::message_count();
            out << "[FAIL] " << c.name << " threw a non-std exception\n";
            out.flush();
            continue;
        }
        if (harness::failures() == before) {
            out << "[ ok ] " << c.name << "\n";
        } else {
            out << "[FAIL] " << c.name << " (" << (harness::message_count() - before_msg)
                << " assertion(s))\n";
        }
        out.flush();
    }
    out << "\n" << run << " tests, " << harness::failures() << " failures\n";
    out.close();
    return harness::failures() == 0 ? 0 : 1;
#else
    ::testing::InitGoogleTest();
    return RUN_ALL_TESTS();
#endif
}

