// benchmarks/exp_hyper_codec.cpp — EXPERIMENT, nesiaha do produkcneho jadra.
// Ciel: 2 GB/s+ encode cez jthread chunking + vysokoradikove delenie + pair-LUT.
// MSVC + GCC (C++20). Bitova zhoda s hexa60::encode povinna.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#if defined(_MSC_VER)
#include <intrin.h>
#endif

#include "hexa60/codec.hpp"

namespace hyper {
// --- data (xorshift64*, rovnake ako benchmark_native.cpp) ---
inline std::vector<uint8_t> make_data(size_t n, uint64_t seed) {
    std::vector<uint8_t> v(n);
    uint64_t x = seed ? seed : 0x9E3779B97F4A7C15ull;
    for (size_t i = 0; i < n; ++i) {
        x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
        v[i] = (uint8_t)((x * 0x2545F4914F6CDD1Dull) >> 56);
    }
    return v;
}
// --- Lemire delenie konstantami (exaktne pre cele u64) ---
// /60: m = ceil(2^69/60) = 0x8888888888888889, q = hi(m*x)>>5
inline uint64_t div60(uint64_t x) {
#if defined(_MSC_VER)
    uint64_t hi = 0;
    _umul128(x, 0x8888888888888889ull, &hi);
    return hi >> 5;
#else
    return (uint64_t)(((unsigned __int128)x *
                       (unsigned __int128)0x8888888888888889ull) >> 69);
#endif
}
// /3600: m = ceil(2^74/3600) = 0x48D159E26AF37C05, q = hi(m*x)>>10.
// m*3600 - 2^74 = 1616 < 2^10 = 1024? NIE -> berieme k=75: m = 0x91A2B3C4D5E6F80A
// je 64b (hranica), preto k=76 s dvoma _umul128? Jednoduchsie: overena cesta
// cez div60 dvakrat: x/3600 = (x/60)/60 — dve Lemire delenia 60, ziadny div.
inline uint64_t div3600(uint64_t x) {
    // (x/60)/60 s korekciou: Lemire /60 je exaktny, kompozicia tiez.
#if defined(_MSC_VER)
    uint64_t hi = 0, q1 = 0;
    _umul128(x, 0x8888888888888889ull, &hi);
    q1 = hi >> 5;
    _umul128(q1, 0x8888888888888889ull, &hi);
    return hi >> 5;
#else
    uint64_t q1 = (uint64_t)(((unsigned __int128)x *
                              (unsigned __int128)0x8888888888888889ull) >> 69);
    return (uint64_t)(((unsigned __int128)q1 *
                       (unsigned __int128)0x8888888888888889ull) >> 69);
#endif
}
// PAIR LUT: x%3600 -> dva znaky naraz (7200 B, L1).
struct Pairs { uint16_t v[3600]; };
inline const Pairs& pairs() {
    static const Pairs t = [] {
        Pairs p{};
        for (int x = 0; x < 3600; ++x)
            p.v[x] = (uint16_t)(((x / 60) << 8) | (x % 60));
        return p;
    }();
    return t;
}
// --- jeden 8B blok -> 11 znakov ---
// Vysokoradikovo: 5x /3600 (Lemire mulhi) + pair-LUT + zvysok <60 bez delenia.
inline void enc_block(uint64_t v, char* o, const char* A, const Pairs& P) {
    uint64_t q = div3600(v);
    uint64_t r = v - q * 3600;
    uint16_t pr = P.v[r];
    o[9] = A[pr >> 8]; o[10] = A[pr & 255]; v = q;
    q = div3600(v); r = v - q * 3600; pr = P.v[r];
    o[7] = A[pr >> 8]; o[8] = A[pr & 255]; v = q;
    q = div3600(v); r = v - q * 3600; pr = P.v[r];
    o[5] = A[pr >> 8]; o[6] = A[pr & 255]; v = q;
    q = div3600(v); r = v - q * 3600; pr = P.v[r];
    o[3] = A[pr >> 8]; o[4] = A[pr & 255]; v = q;
    q = div3600(v); r = v - q * 3600; pr = P.v[r];
    o[1] = A[pr >> 8]; o[2] = A[pr & 255];
    o[0] = A[q];  // q < 60 vzdy (60^11 > 2^64), bez delenia
}
// Jednovlakno (baseline tohto suboru): rovnaka enc_block, 1 thread.
inline void encode_st(const uint8_t* d, size_t n, char* o) {
    const char* A = hexa60::ALPHABET;
    const Pairs& P = pairs();
    size_t full = n / 8;
    for (size_t i = 0; i < full; ++i) {
        uint64_t v = 0;
        for (int k = 0; k < 8; ++k) v = (v << 8) | d[8 * i + k];
        enc_block(v, o + 11 * i, A, P);
    }
    size_t tail = n % 8;
    if (tail) {
        uint64_t v = 0;
        for (size_t k = 0; k < tail; ++k) v = (v << 8) | d[8 * full + k];
        hexa60::detail::write_fixed(v, hexa60::TAIL_CHARS[tail], o + 11 * full);
    }
}
// Multithread: bloky delene po vlaknach, ziadne zamky.
// Kazde vlakno pise disjunktny [out_lo, out_hi) usek.
inline void encode_mt(const uint8_t* d, size_t n, char* o, unsigned nthr) {
    size_t full = n / 8;
    const char* A = hexa60::ALPHABET;
    const Pairs& P = pairs();
    auto worker = [&](size_t blo, size_t bhi) {
        for (size_t i = blo; i < bhi; ++i) {
            const uint8_t* s = d + 8 * i;
            uint64_t v = 0;
            for (int k = 0; k < 8; ++k) v = (v << 8) | s[k];
            enc_block(v, o + 11 * i, A, P);
        }
    };
    if (nthr <= 1 || full < nthr * 4) { worker(0, full); }
    else {
        std::vector<std::jthread> th;
        th.reserve(nthr);
        for (unsigned t = 0; t < nthr; ++t) {
            size_t lo = full * t / nthr, hi = full * (t + 1) / nthr;
            th.emplace_back(worker, lo, hi);
        }
    }
    size_t tail = n % 8;
    if (tail) {
        uint64_t v = 0;
        for (size_t k = 0; k < tail; ++k) v = (v << 8) | d[8 * full + k];
        hexa60::detail::write_fixed(v, hexa60::TAIL_CHARS[tail], o + 11 * full);
    }
}
}  // namespace hyper

template <class F>
static double best_of(F&& f, int reps) {
    using clk = std::chrono::steady_clock;
    double best = 1e99;
    for (int i = 0; i < reps; ++i) {
        auto t0 = clk::now(); f();
        auto t1 = clk::now();
        double s = std::chrono::duration<double>(t1 - t0).count();
        if (s < best) best = s;
    }
    return best;
}

int main() {
    for (uint64_t t : {0ull, 1ull, 59ull, 60ull, 3599ull, 3600ull,
                       0xFFFFFFFFull, 0xFFFFFFFFFFFFFFFFull,
                       0x8000000000000000ull}) {
        if (hyper::div60(t) != t / 60) { std::puts("DIV60 MISMATCH"); return 1; }
        if (hyper::div3600(t) != t / 3600) { std::puts("DIV3600 MISMATCH"); return 1; }
    }
    unsigned hw = std::thread::hardware_concurrency();
    if (!hw) hw = 8;
    std::printf("HW threads: %u\n", hw);
    for (size_t n : {size_t(1000000), size_t(10000000)}) {
        auto data = hyper::make_data(n, n);
        std::string ref = hexa60::encode(data.data(), data.size());
        std::string st(ref.size(), '?'), mt(ref.size(), '?');
        hyper::encode_st(data.data(), n, st.data());
        hyper::encode_mt(data.data(), n, mt.data(), hw);
        bool ok_st = (st == ref), ok_mt = (mt == ref);
        int reps = n <= 1000000 ? 5 : 3;
        for (int i = 0; i < 2; ++i) {
            hyper::encode_st(data.data(), n, st.data());
            hyper::encode_mt(data.data(), n, mt.data(), hw);
        }
        double t_ref = best_of([&] {
            volatile auto w = hexa60::encode(data.data(), data.size()); (void)w;
        }, reps);
        double t_st = best_of([&] { hyper::encode_st(data.data(), n, st.data()); }, reps);
        double t_mt = best_of([&] { hyper::encode_mt(data.data(), n, mt.data(), hw); }, reps);
        double mb = (double)n / 1e6;
        std::printf("n=%zu MB\n", n);
        std::printf("  REF codec.hpp ST : %8.2f MB/s\n", mb / t_ref);
        std::printf("  HYPER single     : %8.2f MB/s  %s (x%.2f vs REF)\n",
                    mb / t_st, ok_st ? "PASS" : "FAIL", t_ref / t_st);
        std::printf("  HYPER jthread-%u  : %8.2f MB/s  %s (x%.2f vs REF)%s\n",
                    hw, mb / t_mt, ok_mt ? "PASS" : "FAIL", t_ref / t_mt,
                    mb / t_mt >= 2000 ? "  >>> 2 GB/s CIEL SPLNENY <<<" : "");
        if (!ok_st || !ok_mt) return 1;
    }
    return 0;
}
