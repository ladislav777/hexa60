#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#if defined(_MSC_VER)
#include <intrin.h>
#endif

#include "hexa60/codec.hpp"

// Lemire: q = x / 60 cez 128-bit sucin.
// m = ceil(2^69/60) = 0x8888888888888889, q = (m*x) >> 69 = hi >> 5.
// Exaktnost: m*60 - 2^69 = 28 < 2^5 = 32 -> presne pre vsetky x < 2^64.
static inline uint64_t div60_lemire(uint64_t x) {
#if defined(_MSC_VER)
    uint64_t hi = 0;
    _umul128(x, 0x8888888888888889ull, &hi);
    return hi >> 5;
#else
    return (uint64_t)(((unsigned __int128)x *
                       (unsigned __int128)0x8888888888888889ull) >> 69);
#endif
}

// --- deterministicke data (xorshift64*, rovnake ako benchmark_native.cpp) ---
static std::vector<uint8_t> make_data(size_t n, uint64_t seed) {
    std::vector<uint8_t> v(n);
    uint64_t x = seed ? seed : 0x9E3779B97F4A7C15ull;
    for (size_t i = 0; i < n; ++i) {
        x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
        v[i] = (uint8_t)((x * 0x2545F4914F6CDD1Dull) >> 56);
    }
    return v;
}

// --- V0: aktualny postup (write_fixed: q=x/60, r=x%60 v cykle) ---
static void enc_v0(uint64_t v, char* out) {
    hexa60::detail::write_fixed(v, 11, out);
}

// --- V1: fused divmod (q=x/60 raz, r=x-q*60), cyklus zachovany ---
static void enc_v1(uint64_t v, char* out) {
    for (int i = 10; i >= 0; --i) {
        uint64_t q = v / 60;
        uint64_t r = v - q * 60;
        out[i] = hexa60::ALPHABET[r];
        v = q;
    }
}

// --- V2: V1 + Lemire delenie 60 (m*x >> 69) ---
static void enc_v2(uint64_t v, char* out) {
    for (int i = 10; i >= 0; --i) {
        uint64_t q = div60_lemire(v);
        uint64_t r = v - q * 60;
        out[i] = hexa60::ALPHABET[r];
        v = q;
    }
}

// --- V3: V2 + plny unroll (11 krokov natvrdo, ziadny cyklus) ---
#define STEP(I, V, Q, R, OUT) \
    Q = div60_lemire(V); \
    R = (V) - Q * 60; \
    (OUT)[I] = hexa60::ALPHABET[R];
static void enc_v3(uint64_t v, char* out) {
    uint64_t q, r;
    STEP(10, v, q, r, out); v = q;
    STEP(9, v, q, r, out); v = q;
    STEP(8, v, q, r, out); v = q;
    STEP(7, v, q, r, out); v = q;
    STEP(6, v, q, r, out); v = q;
    STEP(5, v, q, r, out); v = q;
    STEP(4, v, q, r, out); v = q;
    STEP(3, v, q, r, out); v = q;
    STEP(2, v, q, r, out); v = q;
    STEP(1, v, q, r, out); v = q;
    out[0] = hexa60::ALPHABET[v];
}
#undef STEP

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
    for (size_t n : {size_t(1000000), size_t(10000000)}) {
        auto data = make_data(n, n);
        size_t full = n / 8;
        // referencny vystup z aktualneho kodeku
        std::string ref = hexa60::encode(data.data(), data.size());

        // korektnost: kazdy variant musi dat bitovo rovnaky vystup
        bool ok = true;
        std::string w(ref.size(), '?');
        auto run_variant = [&](auto enc) {
            char* p = w.data();
            for (size_t i = 0; i < full; ++i) {
                uint64_t v = 0;
                for (int k = 0; k < 8; ++k) v = (v << 8) | data[8 * i + k];
                enc(v, p); p += 11;
            }
            size_t tail = n % 8;
            if (tail) {
                uint64_t v = 0;
                for (size_t k = 0; k < tail; ++k) v = (v << 8) | data[8 * full + k];
                hexa60::detail::write_fixed(v, hexa60::TAIL_CHARS[tail], p);
            }
        };
        char probe[11];
        // Lemire musi sediet na celej hranici u64 (nie len par vzoriek)
        for (uint64_t t : {0ull, 1ull, 59ull, 60ull, 61ull, 3599ull, 3600ull,
                           3601ull, 0xFFFFFFFFull, 0x100000000ull,
                           0xFFFFFFFFFFFFFFC4ull /* 2^64-60 */,
                           0xFFFFFFFFFFFFFFFFull, 0x123456789ABCDEF0ull,
                           0x8000000000000000ull, 0x7FFFFFFFFFFFFFFFull}) {
            if (div60_lemire(t) != t / 60) {
                std::printf("LEMIRE MISMATCH t=%llu q=%llu\n",
                            (unsigned long long)t,
                            (unsigned long long)div60_lemire(t));
                return 1;
            }
        }
        for (uint64_t t : {0ull, 1ull, 59ull, 60ull, 3600ull,
                           0xFFFFFFFFFFFFFFFFull, 0x123456789ABCDEF0ull}) {
            char a[11], b[11], c[11], d[11];
            enc_v0(t, a); enc_v1(t, b); enc_v2(t, c); enc_v3(t, d);
            if (memcmp(a, b, 11) || memcmp(a, c, 11) || memcmp(a, d, 11)) ok = false;
            (void)probe;
        }
        run_variant(enc_v0);
        if (w != ref) { std::puts("V0 MISMATCH vs codec.hpp"); return 1; }
        run_variant(enc_v1);
        if (w != ref) { std::puts("V1 MISMATCH"); return 1; }
        run_variant(enc_v2);
        if (w != ref) { std::puts("V2 MISMATCH"); return 1; }
        run_variant(enc_v3);
        if (w != ref) { std::puts("V3 MISMATCH"); return 1; }

        int reps = n <= 1000000 ? 5 : 3;
        for (int i = 0; i < 2; ++i) { run_variant(enc_v0); run_variant(enc_v3); }  // warm-up
        std::string sink(ref.size(), '?');
        auto bench = [&](auto enc) {
            return best_of([&] {
                char* p = sink.data();
                for (size_t i = 0; i < full; ++i) {
                    uint64_t v = 0;
                    for (int k = 0; k < 8; ++k) v = (v << 8) | data[8 * i + k];
                    enc(v, p); p += 11;
                }
            }, reps);
        };
        double t0 = bench(enc_v0), t1 = bench(enc_v1),
               t2 = bench(enc_v2), t3 = bench(enc_v3);
        std::printf("n=%zu full=%zu\n", n, full);
        std::printf("  V0 aktualny (q=x/60, r=x%%60, cyklus) : %8.2f MB/s\n", n / t0 / 1e6);
        std::printf("  V1 fused divmod (r=x-q*60)            : %8.2f MB/s (x%.2f)\n", n / t1 / 1e6, t0 / t1);
        std::printf("  V2 V1 + Lemire/Barrett (/60 -> mul)   : %8.2f MB/s (x%.2f)\n", n / t2 / 1e6, t0 / t2);
        std::printf("  V3 V2 + plny unroll 11 krokov         : %8.2f MB/s (x%.2f)\n", n / t3 / 1e6, t0 / t3);
        std::printf("  korektnost V0..V3 vs codec.hpp: %s\n", ok ? "PASS" : "FAIL");
        if (!ok) return 1;
    }
    return 0;
}
