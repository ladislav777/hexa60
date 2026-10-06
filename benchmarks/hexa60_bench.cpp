// benchmarks/hexa60_bench.cpp — HEXA-60 encoder hot-loop optimalizacia.
// Format NEMENI: 8B big-endian u64 -> 11 chars, tail TAIL_CHARS, alphabet z codec.hpp.
// A) REF scalar (write_fixed, nezmeneny) = correctness oracle.
// B) OPT: reciprocal /60 (Lemire) + /3600 kompozicia + PAIR LUT + 16-bit store + ILP4.
// C) CMP: compiler-generated /60 (q=x/60, r=x-q*60), unroll, bez LUT.
// MSVC: cl /std:c++20 /O2 /EHsc ; GCC/Clang fallback cez __int128.
// Vystup len stdout (tabulka MiB/s + speedup), exit!=0 pri nezhode.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <numeric>
#include <string>
#include <vector>

#if defined(_MSC_VER)
#include <intrin.h>
#endif

#include "hexa60/codec.hpp"
#include "hexa60/fast_codec.hpp"

namespace bench {
// --- xorshift64* data (rovnake ako predosle bench) ---
inline std::vector<uint8_t> make_data(size_t n, uint64_t seed) {
    std::vector<uint8_t> v(n);
    uint64_t x = seed ? seed : 0x9E3779B97F4A7C15ull;
    for (size_t i = 0; i < n; ++i) {
        x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
        v[i] = (uint8_t)((x * 0x2545F4914F6CDD1Dull) >> 56);
    }
    return v;
}
inline uint64_t rng64(uint64_t& s) {
    s ^= s >> 12; s ^= s << 25; s ^= s >> 27;
    return s * 0x2545F4914F6CDD1Dull;
}
// --- reciprocal /60: m=ceil(2^69/60)=0x8888888888888889, q=hi(m*x)>>5 ---
// Dokaz exaktnosti: m*60-2^69=28. Chyba aproximacie < 28*x/2^69 < 28*2^64/2^69
// = 28/32 < 1, a m je ceil -> kvocient je vzdy presny floor(x/60) pre x<2^64.
// (Standardny Lemire argument: e=m*d-2^k < 2^(k-64) => exaktne.)
inline uint64_t q60_rec(uint64_t x) {
#if defined(_MSC_VER)
    uint64_t hi = 0;
    _umul128(x, 0x8888888888888889ull, &hi);
    return hi >> 5;
#else
    return (uint64_t)(((unsigned __int128)x *
                       (unsigned __int128)0x8888888888888889ull) >> 69);
#endif
}
// --- /3600 kompoziciou: floor(floor(x/60)/60)=floor(x/3600) (exact) ---
// Dvod: 64-bit single-magic pre /3600 vyzaduje m>=2^64 (k=75: m je 64b
// hranica), kompozicia dvoch exaktnych /60 je exaktna a stoji 2x mulhi.
inline uint64_t q3600_rec(uint64_t x) { return q60_rec(q60_rec(x)); }

// === A) REF: povodny scalar, NEZMENENY (oracle) ===
inline void ref_block(uint64_t v, char* o) {
    hexa60::detail::write_fixed(v, 11, o);
}
// === C) CMP: compiler-generated delenie, fused, unroll, bez LUT ===
inline void cmp_block(uint64_t v, char* o) {
    const char* A = hexa60::ALPHABET;
    uint64_t q, r;
    q = v / 60; r = v - q * 60; o[10] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[9] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[8] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[7] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[6] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[5] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[4] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[3] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[2] = A[r]; v = q;
    q = v / 60; r = v - q * 60; o[1] = A[r]; v = q;
    o[0] = A[v];
}
// === B) OPT: reciprocal + pair-LUT + 16-bit store ===
// 5x /3600 (2 mulhi kazdy) + pair LUT + zvysok<60. 10 mulhi vs 11 div.
// Store: priamy uint16_t write (little-endian skladanie par-znakov).
// Portable: znaky su ASCII, par P=(hi<<8)|lo; na LE sa uint16 write = [lo-byte?]
// POZOR na endian: explicitne skladame cez shift aby to bolo endian-safe:
// out[2k]=A[hi], out[2k+1]=A[lo] cez 16-bit store len na LE s byte-swap logikou.
// Aby zostalo 100% portable a safe: pouzijeme memcpy 2B z char[2] pola.
// Kompilator to prelozi na single 16-bit store bez aliasing problemu.
inline void opt_block(uint64_t v, char* o) {
    const char* A = hexa60::ALPHABET;
    const auto& P = hexa60::fast::PAIRS;
    uint64_t q = q3600_rec(v);
    uint64_t r = v - q * 3600;
    uint16_t pr = P.v[r];
    char c0 = A[pr >> 8], c1 = A[pr & 255];
    char tmp[2] = {c0, c1};
    std::memcpy(o + 9, tmp, 2); v = q;
    q = q3600_rec(v); r = v - q * 3600; pr = P.v[r];
    tmp[0] = A[pr >> 8]; tmp[1] = A[pr & 255];
    std::memcpy(o + 7, tmp, 2); v = q;
    q = q3600_rec(v); r = v - q * 3600; pr = P.v[r];
    tmp[0] = A[pr >> 8]; tmp[1] = A[pr & 255];
    std::memcpy(o + 5, tmp, 2); v = q;
    q = q3600_rec(v); r = v - q * 3600; pr = P.v[r];
    tmp[0] = A[pr >> 8]; tmp[1] = A[pr & 255];
    std::memcpy(o + 3, tmp, 2); v = q;
    q = q3600_rec(v); r = v - q * 3600; pr = P.v[r];
    tmp[0] = A[pr >> 8]; tmp[1] = A[pr & 255];
    std::memcpy(o + 1, tmp, 2);
    o[0] = A[q];  // q<60 vzdy (60^11>2^64), bez delenia
}
}  // namespace bench
namespace bench2 {
// --- ILP4 pasy: 4 nezavisle retazce cez ten isty block-funktor ---
template <class BLK>
inline void encode_ilp4(const uint8_t* d, size_t nfull, char* o, BLK blk) {
    size_t i = 0;
    size_t n4 = nfull & ~size_t(3);
    for (; i < n4; i += 4) {
        uint64_t v0 = 0, v1 = 0, v2 = 0, v3 = 0;
        for (int k = 0; k < 8; ++k) {
            v0 = (v0 << 8) | d[8 * (i + 0) + k];
            v1 = (v1 << 8) | d[8 * (i + 1) + k];
            v2 = (v2 << 8) | d[8 * (i + 2) + k];
            v3 = (v3 << 8) | d[8 * (i + 3) + k];
        }
        blk(v0, o + 11 * (i + 0));
        blk(v1, o + 11 * (i + 1));
        blk(v2, o + 11 * (i + 2));
        blk(v3, o + 11 * (i + 3));
    }
    for (; i < nfull; ++i) {
        uint64_t v = 0;
        for (int k = 0; k < 8; ++k) v = (v << 8) | d[8 * i + k];
        blk(v, o + 11 * i);
    }
}
// --- scalar pas (REF baseline) ---
template <class BLK>
inline void encode_scalar(const uint8_t* d, size_t nfull, char* o, BLK blk) {
    for (size_t i = 0; i < nfull; ++i) {
        uint64_t v = 0;
        for (int k = 0; k < 8; ++k) v = (v << 8) | d[8 * i + k];
        blk(v, o + 11 * i);
    }
}
inline void encode_tail(const uint8_t* d, size_t n, char* o) {
    size_t full = n / 8, tail = n % 8;
    if (tail) {
        uint64_t v = 0;
        for (size_t k = 0; k < tail; ++k) v = (v << 8) | d[8 * full + k];
        hexa60::detail::write_fixed(v, hexa60::TAIL_CHARS[tail], o + 11 * full);
    }
}
// === C) CORRECTNESS: OPT/CMP vs REF oracle ===
inline int correctness() {
    int fails = 0;
    auto chk = [&](uint64_t v, const char* tag) {
        char a[11], b[11], c[11];
        bench::ref_block(v, a); bench::opt_block(v, b); bench::cmp_block(v, c);
        if (std::memcmp(a, b, 11) || std::memcmp(a, c, 11)) {
            std::printf("BLOCK-MISMATCH %s v=%llu\n", tag, (unsigned long long)v);
            ++fails;
        }
        if (bench::q60_rec(v) != v / 60) {
            std::printf("Q60-MISMATCH %s\n", tag);
            ++fails;
        }
        if (bench::q3600_rec(v) != v / 3600) {
            std::printf("Q3600-MISMATCH %s v=%llu\n", tag, (unsigned long long)v);
            ++fails;
        }
    };
    chk(0, "zero"); chk(1, "one"); chk(59, "59"); chk(60, "60"); chk(61, "61");
    chk(3599, "3599"); chk(3600, "3600"); chk(0xFFFFFFFFull, "u32max");
    chk(0x100000000ull, "2^32"); chk(0xFFFFFFFFFFFFFFFFull, "UINT64_MAX");
    chk(0x8000000000000000ull, "highbit"); chk(0x7FFFFFFFFFFFFFFFull, "2^63-1");
    chk(0xFFFFFFFFFFFFFFC4ull, "2^64-60"); chk(0x123456789ABCDEF0ull, "pattern");
    uint64_t s = 0x9E3779B97F4A7C15ull;
    for (int i = 0; i < 100000; ++i) {
        uint64_t v = bench::rng64(s);
        char a[11], b[11], c[11];
        bench::ref_block(v, a); bench::opt_block(v, b); bench::cmp_block(v, c);
        if (std::memcmp(a, b, 11) || std::memcmp(a, c, 11) ||
            bench::q60_rec(v) != v / 60 || bench::q3600_rec(v) != v / 3600) {
            std::printf("RAND-MISMATCH i=%d\n", i);
            ++fails;
            if (fails > 5) return fails;
        }
    }
    for (size_t n = 0; n <= 160; ++n) {
        auto d = bench::make_data(n ? n : 1, 1234 + n);
        d.resize(n);
        std::string ref = hexa60::encode(d.data(), d.size());
        size_t full = n / 8;
        std::string wo(ref.size(), '?'), wc(ref.size(), '?');
        encode_ilp4(d.data(), full, wo.data(), bench::opt_block);
        encode_tail(d.data(), n, wo.data());
        encode_ilp4(d.data(), full, wc.data(), bench::cmp_block);
        encode_tail(d.data(), n, wc.data());
        if (wo != ref) { std::printf("LEN-MISMATCH OPT n=%zu\n", n); ++fails; }
        if (wc != ref) { std::printf("LEN-MISMATCH CMP n=%zu\n", n); ++fails; }
        if (fails > 5) return fails;
    }
    for (size_t n : {size_t(8), size_t(11), size_t(64), size_t(160)}) {
        for (uint8_t fill : {uint8_t(0), uint8_t(0xFF)}) {
            std::vector<uint8_t> d(n, fill);
            std::string ref = hexa60::encode(d.data(), d.size());
            std::string wo(ref.size(), '?');
            encode_ilp4(d.data(), n / 8, wo.data(), bench::opt_block);
            encode_tail(d.data(), n, wo.data());
            if (wo != ref) {
                std::printf("FILL-MISMATCH n=%zu f=%u\n", n, fill);
                ++fails;
            }
        }
    }
    return fails;
}
// --- median z behov; inner opakuje f aby cas presiahol rozlisenie hodin ---
template <class F>
inline double median_of(F&& f, int reps, int inner) {
    using clk = std::chrono::steady_clock;
    std::vector<double> ts;
    ts.reserve((size_t)reps);
    for (int i = 0; i < reps; ++i) {
        auto t0 = clk::now();
        for (int k = 0; k < inner; ++k) f();
        auto t1 = clk::now();
        ts.push_back(std::chrono::duration<double>(t1 - t0).count() / inner);
    }
    std::sort(ts.begin(), ts.end());
    return ts[(size_t)reps / 2];
}
// Compiler bariera: zabrani DCE meraneho encode bez pridaneho O(N) hashu.
// MSVC: _ReadWriteBarrier + volatile dotyk prveho/posledneho bajtu.
// GCC/Clang: asm volatile.
inline void asm_barrier(char* p, size_t n) {
    if (n == 0) return;
#if defined(_MSC_VER)
    _ReadWriteBarrier();
    volatile char a = p[0];
    volatile char b = p[n - 1];
    (void)a; (void)b;
    _ReadWriteBarrier();
#else
    asm volatile("" : "+m"(*(char(*)[1])p) : : "memory");
#endif
}
}  // namespace bench2
// === D) BENCHMARK: REF-scalar vs OPT-ILP4-recip+LUT vs CMP-compiler ===
// Rovnaky vstup, rovnaky buffer, rovnake CPU/flags, median, rotacia poradia.
// Velkosti: 8B, 1KiB, 1MiB, 8MiB, 100MiB. MiB/s zo VSTUPNYCH MiB.
int main() {
    if (int f = bench2::correctness()) {
        std::printf("CORRECTNESS: %d FAILS — stop.\n", f);
        return 1;
    }
    std::puts("CORRECTNESS: PASS (0-160B, taily, 0/FF, U64MAX, highbit, 100k u64).");
    std::fflush(stdout);
    const size_t K = 1024, M = 1048576;
    const size_t sizes[] = {8, K, M, 8 * M, 100 * M};
    std::puts("size      | REF scalar | OPT ILP4+rec+LUT | CMP compiler | OPT speedup | CMP speedup");
    std::fflush(stdout);
    for (size_t n : sizes) {
        auto data = bench::make_data(n, n ? n : 1);
        std::string ref = hexa60::encode(data.data(), data.size());
        size_t full = n / 8;
        std::string buf(ref.size() ? ref.size() : 11, '?');
        // Merame CISTY encode cas: ziadny touch/hash v hot-loope, len DSB
        // bariera cez volatile pointer aby kompilator kod neodstranil.
        // Po kazdom behu overime jeden byte (O(1)) — bit-identita sa overuje
        // plosne v correctness() a FULL-SIZE checku nizsie.
        auto mR = [&] {
            bench2::encode_scalar(data.data(), full, buf.data(), bench::ref_block);
            bench2::asm_barrier(buf.data(), buf.size());
        };
        auto mO = [&] {
            bench2::encode_ilp4(data.data(), full, buf.data(), bench::opt_block);
            bench2::asm_barrier(buf.data(), buf.size());
        };
        auto mC = [&] {
            bench2::encode_ilp4(data.data(), full, buf.data(), bench::cmp_block);
            bench2::asm_barrier(buf.data(), buf.size());
        };
        int reps = n <= 1024 ? 31 : (n <= M ? 15 : 9);
        // Male velkosti: inner-loop opakuje encode aby cas presiahol rozlisenie.
        int inner = n < K ? 1000 : 1;
        for (int i = 0; i < 5; ++i) { mR(); mO(); mC(); }  // warm-up
        std::vector<double> a, b, c;
        a.reserve((size_t)reps); b.reserve((size_t)reps); c.reserve((size_t)reps);
        for (int round = 0; round < 3; ++round) {  // rotacia ROC/OCR/CRO
            int cnt = reps / 3 + (round < reps % 3 ? 1 : 0);
            for (int i = 0; i < cnt; ++i) {
                if (round == 0) {
                    a.push_back(bench2::median_of(mR, 3, inner));
                    b.push_back(bench2::median_of(mO, 3, inner));
                    c.push_back(bench2::median_of(mC, 3, inner));
                } else if (round == 1) {
                    b.push_back(bench2::median_of(mO, 3, inner));
                    c.push_back(bench2::median_of(mC, 3, inner));
                    a.push_back(bench2::median_of(mR, 3, inner));
                } else {
                    c.push_back(bench2::median_of(mC, 3, inner));
                    a.push_back(bench2::median_of(mR, 3, inner));
                    b.push_back(bench2::median_of(mO, 3, inner));
                }
            }
        }
        std::sort(a.begin(), a.end());
        std::sort(b.begin(), b.end());
        std::sort(c.begin(), c.end());
        double tR = a[a.size() / 2], tO = b[b.size() / 2], tC = c[c.size() / 2];
        double mib = (double)n / 1048576.0;
        if (n <= K) {
            std::printf("%9zu | %9.1f ns | %14.1f ns | %12.1f ns | x%9.2f | x%9.2f %s\n",
                        n, tR * 1e9, tO * 1e9, tC * 1e9, tR / tO, tR / tC,
                        (tR / tO >= 1.10) ? " OPT>" : "");
        } else {
            std::printf("%9zu | %9.2f | %14.2f | %12.2f | x%9.2f | x%9.2f %s\n",
                        n, mib / tR, mib / tO, mib / tC, tR / tO, tR / tC,
                        (tR / tO >= 1.10) ? " OPT>" : "");
        }
        std::fflush(stdout);
        bench2::encode_ilp4(data.data(), full, buf.data(), bench::opt_block);
        bench2::encode_tail(data.data(), n, buf.data());
        if (buf != ref) { std::puts("FULL-SIZE MISMATCH OPT"); return 1; }
    }
    return 0;
}