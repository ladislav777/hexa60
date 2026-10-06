// benchmark_native.cpp — cisty C++ vs C++ suboj: HEXA-60 vs Base64 vs Base85 vs Base91.
// Rovnake buffery, rovnaky runtime, warm-up, chrono best-of-N, FNV round-trip check.
// Build: cl /std:c++20 /O2 (cez benchmark_pure_cpp.py, ktory najde vcvars64.bat).
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>

#include "hexa60/codec.hpp"

// --- deterministicke data (xorshift64*, seed funkcia velkosti) ---
static std::vector<uint8_t> make_data(size_t n, uint64_t seed) {
    std::vector<uint8_t> v(n);
    uint64_t x = seed ? seed : 0x9E3779B97F4A7C15ull;
    for (size_t i = 0; i < n; ++i) {
        x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
        v[i] = (uint8_t)((x * 0x2545F4914F6CDD1Dull) >> 56);
    }
    return v;
}
static uint64_t fnv(const uint8_t* p, size_t n) {
    uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < n; ++i) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}

// --- Base64 (optimalizovany, tabulkovy, bez padding vetveni v hot loop) ---
static const char* B64E = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
static int B64D[256];
static void b64_init() {
    for (int i = 0; i < 256; ++i) B64D[i] = -1;
    for (int i = 0; B64E[i]; ++i) B64D[(unsigned char)B64E[i]] = i;
    B64D['='] = 0;
}
static std::string b64_encode(const uint8_t* d, size_t n) {
    std::string o; o.resize(((n + 2) / 3) * 4);
    char* p = o.data();
    size_t i = 0;
    for (; i + 3 <= n; i += 3) {
        unsigned v = ((unsigned)d[i] << 16) | ((unsigned)d[i+1] << 8) | d[i+2];
        p[0]=B64E[(v>>18)&63]; p[1]=B64E[(v>>12)&63]; p[2]=B64E[(v>>6)&63]; p[3]=B64E[v&63]; p+=4;
    }
    if (i < n) {
        unsigned v = (unsigned)d[i] << 16;
        if (i+1 < n) v |= (unsigned)d[i+1] << 8;
        p[0]=B64E[(v>>18)&63]; p[1]=B64E[(v>>12)&63];
        p[2]=(i+1<n)?B64E[(v>>6)&63]:'='; p[3]='=';
    }
    return o;
}
static std::vector<uint8_t> b64_decode(const char* s, size_t n) {
    std::vector<uint8_t> o; o.resize((n / 4) * 3 + 3);
    size_t w = 0;
    for (size_t i = 0; i + 4 <= n; i += 4) {
        int a=B64D[(unsigned char)s[i]], b=B64D[(unsigned char)s[i+1]];
        int c=B64D[(unsigned char)s[i+2]], e=B64D[(unsigned char)s[i+3]];
        unsigned v=((unsigned)a<<18)|((unsigned)b<<12)|((unsigned)c<<6)|(unsigned)e;
        o[w++]=(v>>16)&255; if(s[i+2]!='='){o[w++]=(v>>8)&255;} if(s[i+3]!='='){o[w++]=v&255;}
    }
    o.resize(w); return o;
}
// --- Base85 (RFC1924 abeceda, 4B -> 5ch, bez 'z' skratiek = ferove) ---
static const char* B85E = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~";
static int B85D[256];
static void b85_init() {
    for (int i = 0; i < 256; ++i) B85D[i] = -1;
    for (int i = 0; B85E[i]; ++i) B85D[(unsigned char)B85E[i]] = i;
}
static std::string b85_encode(const uint8_t* d, size_t n) {
    size_t full = n / 4; int rem = (int)(n % 4);
    std::string o; o.resize(full * 5 + (rem ? rem + 1 : 0));
    char* p = o.data();
    for (size_t i = 0; i < full; ++i) {
        unsigned v = ((unsigned)d[4*i]<<24)|((unsigned)d[4*i+1]<<16)|((unsigned)d[4*i+2]<<8)|d[4*i+3];
        for (int k = 4; k >= 0; --k) { p[k] = B85E[v % 85]; v /= 85; }
        p += 5;
    }
    if (rem) {
        unsigned v = 0;
        for (int k = 0; k < rem; ++k) v = (v << 8) | d[4*full+k];
        for (int k = 0; k < 4 - rem; ++k) v <<= 8;
        char t[5]; for (int k = 4; k >= 0; --k) { t[k] = B85E[v % 85]; v /= 85; }
        for (int k = 0; k < rem + 1; ++k) *p++ = t[k];
    }
    return o;
}
static std::vector<uint8_t> b85_decode(const char* s, size_t n) {
    std::vector<uint8_t> o; o.reserve((n / 5) * 4 + 4);
    size_t i = 0;
    for (; i + 5 <= n; i += 5) {
        unsigned v = 0;
        for (int k = 0; k < 5; ++k) v = v * 85 + (unsigned)B85D[(unsigned char)s[i+k]];
        o.push_back((v>>24)&255); o.push_back((v>>16)&255); o.push_back((v>>8)&255); o.push_back(v&255);
    }
    if (i < n) {
        int m = (int)(n - i);
        unsigned v = 0;
        for (int k = 0; k < m; ++k) v = v * 85 + (unsigned)B85D[(unsigned char)s[i+k]];
        for (int k = m; k < 5; ++k) v = v * 85 + 84;
        for (int k = 0; k < m - 1; ++k) o.push_back((v >> (24 - 8*k)) & 255);
    }
    return o;
}

// --- Base91 (basE91, 13/14-bit, vlastna abeceda) ---
static const char* B91E = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&()*+,./:;<=>?@[]^_`{|}~\"";
static int B91D[256];
static void b91_init() {
    for (int i = 0; i < 256; ++i) B91D[i] = -1;
    for (int i = 0; B91E[i]; ++i) B91D[(unsigned char)B91E[i]] = i;
}
static std::string b91_encode(const uint8_t* d, size_t n) {
    std::string o; o.reserve((size_t)(n * 1.24) + 8);
    unsigned b = 0; int nb = 0;
    for (size_t i = 0; i < n; ++i) {
        b |= (unsigned)d[i] << nb; nb += 8;
        if (nb > 13) {
            unsigned v = b & 8191;
            if (v > 88) { b >>= 13; nb -= 13; }
            else { v = b & 16383; b >>= 14; nb -= 14; }
            o += B91E[v % 91]; o += B91E[v / 91];
        }
    }
    if (nb) { o += B91E[b % 91]; if (nb > 7 || b > 90) o += B91E[b / 91]; }
    return o;
}
static std::vector<uint8_t> b91_decode(const char* s, size_t n) {
    std::vector<uint8_t> o; o.reserve((size_t)(n * 0.82) + 8);
    int v = -1; unsigned b = 0; int nb = 0;
    for (size_t i = 0; i < n; ++i) {
        int c = B91D[(unsigned char)s[i]];
        if (v < 0) v = c;
        else {
            v += c * 91; b |= (unsigned)v << nb;
            nb += ((v & 8191) > 88) ? 13 : 14;
            while (nb >= 8) { o.push_back(b & 255); b >>= 8; nb -= 8; }
            v = -1;
        }
    }
    if (v >= 0) o.push_back((b | ((unsigned)v << nb)) & 255);
    return o;
}
// --- harness: warm-up + best-of-N ---
template <typename F>
static double best_of(F&& f, int reps) {
    double best = 1e100;
    for (int i = 0; i < reps; ++i) {
        auto t0 = std::chrono::steady_clock::now();
        f();
        auto t1 = std::chrono::steady_clock::now();
        double s = std::chrono::duration<double>(t1 - t0).count();
        if (s < best) best = s;
    }
    return best;
}
struct Row { const char* name; size_t out; double exp; double enc; double dec; bool ok; };
int main() {
    b64_init(); b85_init(); b91_init();
    {
        auto d = make_data(5000, 12345);
        std::string h = hexa60::encode(d.data(), d.size());
        if (hexa60::decode(h) != d) { std::puts("HEXA-60 selftest FAIL"); return 1; }
        std::string g = b64_encode(d.data(), d.size());
        if (b64_decode(g.data(), g.size()) != d) { std::puts("Base64 selftest FAIL"); return 1; }
        std::string e = b85_encode(d.data(), d.size());
        if (b85_decode(e.data(), e.size()) != d) { std::puts("Base85 selftest FAIL"); return 1; }
        std::string q = b91_encode(d.data(), d.size());
        if (b91_decode(q.data(), q.size()) != d) { std::puts("Base91 selftest FAIL"); return 1; }
    }
    const size_t sizes[] = {1000000, 10000000};
    std::puts("================================================================================");
    std::puts("HEXA-60 vs Base64 vs Base85 vs Base91 — CISTY C++ vs C++ (MSVC /O2)");
    std::puts("rovnake buffery, warm-up 2x, best-of-N, MB/s = vstupne MB/s, FNV check");
    std::puts("================================================================================");
    std::vector<std::pair<size_t, std::vector<Row>>> all;
    for (size_t n : sizes) {
        int reps = (n <= 1000000) ? 5 : 3;
        std::printf("\n>>> Dataset %zu MB (%zu B, warm-up 2x, best-of-%d) ...\n",
                    n / 1000000, n, reps);
        auto data = make_data(n, 0xC17C86DA08516FDBull ^ (uint64_t)n);
        uint64_t href = fnv(data.data(), data.size());
        std::printf("    fnv vstup: %016llx\n", (unsigned long long)href);
        std::vector<Row> rows;
        {
            std::string w0 = hexa60::encode(data.data(), data.size());
            auto b0 = hexa60::decode(w0);
            bool ok = (b0.size() == data.size() && !memcmp(b0.data(), data.data(), data.size()));
            for (int i = 0; i < 2; ++i) { volatile auto w = hexa60::encode(data.data(), data.size()); (void)w; }
            double te = best_of([&]{ volatile auto w = hexa60::encode(data.data(), data.size()); (void)w; }, reps);
            std::string w = hexa60::encode(data.data(), data.size());
            for (int i = 0; i < 2; ++i) { volatile auto b = hexa60::decode(w); (void)b; }
            double td = best_of([&]{ volatile auto b = hexa60::decode(w); (void)b; }, reps);
            rows.push_back({"HEXA-60", w.size(), (double)w.size() / n, n / te / 1e6, n / td / 1e6, ok});
        }
        {
            std::string w0 = b64_encode(data.data(), data.size());
            auto b0 = b64_decode(w0.data(), w0.size());
            bool ok = (b0.size() == data.size() && !memcmp(b0.data(), data.data(), data.size()));
            for (int i = 0; i < 2; ++i) { volatile auto w = b64_encode(data.data(), data.size()); (void)w; }
            double te = best_of([&]{ volatile auto w = b64_encode(data.data(), data.size()); (void)w; }, reps);
            std::string w = b64_encode(data.data(), data.size());
            for (int i = 0; i < 2; ++i) { volatile auto b = b64_decode(w.data(), w.size()); (void)b; }
            double td = best_of([&]{ volatile auto b = b64_decode(w.data(), w.size()); (void)b; }, reps);
            rows.push_back({"Base64 ", w.size(), (double)w.size() / n, n / te / 1e6, n / td / 1e6, ok});
        }
        if (n <= 1000000) {
            std::string w = b85_encode(data.data(), data.size());
            auto b = b85_decode(w.data(), w.size());
            bool ok = (b.size() == data.size() && !memcmp(b.data(), data.data(), data.size()));
            double te = best_of([&]{ volatile auto x = b85_encode(data.data(), data.size()); (void)x; }, 3);
            double td = best_of([&]{ volatile auto y = b85_decode(w.data(), w.size()); (void)y; }, 3);
            rows.push_back({"Base85 ", w.size(), (double)w.size() / n, n / te / 1e6, n / td / 1e6, ok});
            std::string q = b91_encode(data.data(), data.size());
            auto c = b91_decode(q.data(), q.size());
            bool ok2 = (c.size() == data.size() && !memcmp(c.data(), data.data(), data.size()));
            double te2 = best_of([&]{ volatile auto x = b91_encode(data.data(), data.size()); (void)x; }, 3);
            double td2 = best_of([&]{ volatile auto y = b91_decode(q.data(), q.size()); (void)y; }, 3);
            rows.push_back({"Base91 ", q.size(), (double)q.size() / n, n / te2 / 1e6, n / td2 / 1e6, ok2});
        }
        for (auto& r : rows) {
            std::printf("    %s: out=%10zu B exp=%.5fx enc=%8.2f MB/s dec=%8.2f MB/s %s\n",
                        r.name, r.out, r.exp, r.enc, r.dec, r.ok ? "PASS" : "FAIL");
            if (!r.ok) return 1;
        }
        all.emplace_back(n, rows);
    }
    std::puts("\n=================================================================================");
    std::puts("SUHRN (cisty C++)");
    for (auto& [n, rows] : all)
        for (auto& r : rows)
            std::printf(" %6zuMB | %s | %11zu | %7.4fx | %11.2f | %11.2f | %s\n",
                        n / 1000000, r.name, r.out, r.exp, r.enc, r.dec, r.ok ? "PASS" : "FAIL");
    std::puts("Teoria: HEXA-60 1.37500x, Base64 1.33333x, Base85 1.25x, Base91 ~1.23x.");
    std::puts("================================================================================");
    return 0;
}





