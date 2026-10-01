cmake_minimum_required(VERSION 3.16)
project(hexa60_cpp VERSION 1.0.0 LANGUAGES CXX)

# ---------------------------------------------------------------- the library
# Header-only: an INTERFACE target carries the include path and the C++20
# requirement, so consumers get both without linking anything.
add_library(hexa60 INTERFACE)
add_library(hexa60::hexa60 ALIAS hexa60)

target_include_directories(hexa60 INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>)

target_compile_features(hexa60 INTERFACE cxx_std_20)

# ---------------------------------------------------------------- demo
add_executable(hexa60_demo main.cpp)
target_link_libraries(hexa60_demo PRIVATE hexa60)
target_compile_features(hexa60_demo PRIVATE cxx_std_20)

if (MSVC)
    target_compile_options(hexa60_demo PRIVATE /W4 /permissive-)
else()
    target_compile_options(hexa60_demo PRIVATE -Wall -Wextra -Wpedantic)
endif()

# ---------------------------------------------------------------- tests
# Two modes, selected with -DHEXA60_USE_GTEST=ON or OFF (default OFF):
#
#   OFF (default) -- build the test suite with a tiny built-in harness, no
#                    external dependency.
#   ON            -- build against a real GoogleTest, located via
#                    find_package.
#
# The test file compiles in both modes: without HEXA60_NO_GTEST it uses
# gtest macros, with it the local harness.
option(HEXA60_USE_GTEST "Build tests against GoogleTest" OFF)

if (HEXA60_USE_GTEST)
    find_package(GTest REQUIRED)
    include(GoogleTest)
    enable_testing()
    add_executable(hexa60_tests test_hexa60.cpp)
    target_link_libraries(hexa60_tests PRIVATE hexa60 GTest::gtest GTest::gtest_main)
    target_compile_features(hexa60_tests PRIVATE cxx_std_20)
    if (MSVC)
        target_compile_options(hexa60_tests PRIVATE /W4)
    else()
        target_compile_options(hexa60_tests PRIVATE -Wall -Wextra)
    endif()
    add_test(NAME hexa60_tests COMMAND hexa60_tests)
else()
    message(STATUS
        "HEXA60_USE_GTEST=OFF: building the standalone test suite. "
        "Set -DHEXA60_USE_GTEST=ON if GoogleTest is available.")
    enable_testing()
    add_executable(hexa60_tests test_hexa60.cpp)
    target_link_libraries(hexa60_tests PRIVATE hexa60)
    target_compile_definitions(hexa60_tests PRIVATE HEXA60_NO_GTEST)
    target_compile_features(hexa60_tests PRIVATE cxx_std_20)
    if (MSVC)
        target_compile_options(hexa60_tests PRIVATE /W4 /permissive-)
    else()
        target_compile_options(hexa60_tests PRIVATE -Wall -Wextra -Wpedantic)
    endif()
    add_test(NAME hexa60_tests COMMAND hexa60_tests)
endif()

# ---------------------------------------------------------------- install
include(GNUInstallDirs)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(TARGETS hexa60 EXPORT hexa60Targets)
install(EXPORT hexa60Targets
        FILE hexa60Targets.cmake
        NAMESPACE hexa60::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/hexa60)
