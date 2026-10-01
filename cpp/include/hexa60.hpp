// hexa60.hpp -- umbrella header pulling in every module.
//
// Header-only, C++20, zero external dependencies. Just include this and you
// get the codec, the integer type, fractions and the tensor helpers.
//
//   #include "hexa60.hpp"
//
// The individual headers under include/hexa60/ are self-contained and can be
// included individually if you want to keep compile times down.

#ifndef HEXA60_HPP
#define HEXA60_HPP

#include "hexa60/codec.hpp"
#include "hexa60/fraction.hpp"
#include "hexa60/int.hpp"
#include "hexa60/tensor.hpp"

namespace hexa60 {

/// Library version. Matches the Python reference package version.
inline constexpr int VERSION_MAJOR = 1;
inline constexpr int VERSION_MINOR = 0;
inline constexpr int VERSION_PATCH = 0;

}  // namespace hexa60

#endif  // HEXA60_HPP
