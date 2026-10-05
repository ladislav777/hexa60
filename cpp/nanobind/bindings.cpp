// ============================================================================
// HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
// Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
//
// PROPRIETARY AND CONFIDENTIAL SOFTWARE.
// Unauthorized copying, distribution, or modification of this file, via any
// medium, is strictly prohibited under applicable copyright laws and B2B EULA.
// ============================================================================

// _hexa60c -- nanobind accelerator for the HEXA60 chunked codec.
#ifndef PY_SSIZE_T_CLEAN
#define PY_SSIZE_T_CLEAN
#endif
//
// Wraps hexa60::fast (cpp/include/hexa60/fast_codec.hpp) for Python:
//   encode_chunked(data)   -> str   (buffer protocol, zero copy input)
//   decode_chunked(text, strict) -> bytes (PEP-393 kind-aware str access)
//
// GIL policy: released only for inputs larger than GIL_FREE_THRESHOLD
// (4 KiB) -- below that the acquire/release overhead exceeds the work.
//
// ERROR CONTRACT with hexa60.py (translated to the real Python exceptions
// there, so both paths raise the identical class with identical arguments):
//   std::invalid_argument("invalid_char|<pos>|<codepoint>")
//   std::invalid_argument("invalid_layout|<rem>")
//   std::invalid_argument("overflow|<n_chars>|<n_bytes>")
// Anything else escaping here is a bug and surfaces as ValueError/TypeError
// with the original message; the pure fallback remains fully tested.
#ifndef HEXA60_BINDINGS_CPP
#define HEXA60_BINDINGS_CPP

#include <nanobind/nanobind.h>
#include <nanobind/stl/string.h>

#include <Python.h>

#include <cstdint>
#include <span>
#include <stdexcept>
#include <string>
#include <vector>

#include "hexa60/fast_codec.hpp"

namespace nb = nanobind;

namespace {

// Inputs larger than this release the GIL around the core codec call.
constexpr std::size_t GIL_FREE_THRESHOLD = 4096;

[[noreturn]] void raise(const std::string& code) {
    throw std::invalid_argument(code);
}

std::string encode_chunked(nb::handle data) {
    Py_buffer view{};
    if (PyObject_GetBuffer(data.ptr(), &view, PyBUF_SIMPLE) != 0) {
        // hexa60.py validates the type before calling, so this is defensive.
        PyErr_Clear();
        raise("invalid_buffer|encode_chunked expects a bytes-like object");
    }
    const std::size_t n = static_cast<std::size_t>(view.len);
    std::string out(hexa60::fast::encoded_len(n), '\0');
    const auto* src = static_cast<const std::uint8_t*>(view.buf);
    if (n > GIL_FREE_THRESHOLD) {
        nb::gil_scoped_release nogil;
        hexa60::fast::encode(std::span<const std::uint8_t>(src, n), out.data());
    } else {
        hexa60::fast::encode(std::span<const std::uint8_t>(src, n), out.data());
    }
    PyBuffer_Release(&view);
    return out;
}

nb::bytes decode_chunked(nb::str text, bool strict) {
    PyObject* p = text.ptr();
    const std::size_t len = static_cast<std::size_t>(PyUnicode_GET_LENGTH(p));
    if (len == 0) return nb::bytes("", 0);

    // Zero-copy: point directly at the PEP-393 character storage; `kind`
    // selects the code point width. The str object stays referenced by the
    // argument for the whole call, so the pointer is stable without the GIL.
    const int kind = PyUnicode_KIND(p);
    const void* data = PyUnicode_DATA(p);

    // The byte output is always shorter than the character input.
    std::vector<std::uint8_t> out(len);
    hexa60::fast::DecResult r{};

    auto run = [&](auto get) {
        if (len > GIL_FREE_THRESHOLD) {
            nb::gil_scoped_release nogil;
            r = hexa60::fast::decode(len, get, strict, out.data());
        } else {
            r = hexa60::fast::decode(len, get, strict, out.data());
        }
    };

    switch (kind) {
        case 1: {
            const auto* d = static_cast<const std::uint8_t*>(data);
            run([d](std::size_t i) { return static_cast<std::uint32_t>(d[i]); });
            break;
        }
        case 2: {
            const auto* d = static_cast<const std::uint16_t*>(data);
            run([d](std::size_t i) { return static_cast<std::uint32_t>(d[i]); });
            break;
        }
        default: {  // kind 4 (PyUnicode_32BIT_KIND)
            const auto* d = static_cast<const std::uint32_t*>(data);
            run([d](std::size_t i) { return d[i]; });
            break;
        }
    }

    switch (r.err) {
        case hexa60::fast::Err::Ok:
            return nb::bytes(reinterpret_cast<const char*>(out.data()), r.size);
        case hexa60::fast::Err::BadChar:
            raise("invalid_char|" + std::to_string(r.pos) + "|" +
                  std::to_string(r.cp));
        case hexa60::fast::Err::BadLayout:
            raise("invalid_layout|" + std::to_string(r.rem));
        case hexa60::fast::Err::Overflow:
            raise("overflow|" + std::to_string(r.n_chars) + "|" +
                  std::to_string(r.n_bytes));
    }
    raise("internal|unreachable");  // keeps the compiler happy
}

}  // namespace

NB_MODULE(_hexa60c, m) {
    m.doc() = "HEXA60 native chunked codec (L1-pair-LUT, C++20, nanobind)";
    // hexa60.py refuses to bind a module with a different ABI version.
    m.attr("ABI_VERSION") = 1;
    m.attr("PAIR_LUT_BYTES") = 7200;
    m.attr("GIL_FREE_THRESHOLD") = GIL_FREE_THRESHOLD;
    m.def("encode_chunked", &encode_chunked, nb::arg("data"),
          "bytes-like -> chunked Base-60 text (8 bytes -> 11 chars)");
    m.def("decode_chunked", &decode_chunked, nb::arg("text"),
          nb::arg("strict") = false,
          "chunked Base-60 text -> bytes; raises ValueError with a "
          "structured code that hexa60.py converts to the real exception");
}

#endif  // HEXA60_BINDINGS_CPP
