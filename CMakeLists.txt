cmake_minimum_required(VERSION 3.16)
project(path_tracer_denoiser LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_library(pt_core
  src/renderer.cpp
  src/denoiser.cpp
  src/metrics.cpp
)

target_include_directories(pt_core PUBLIC src)
target_compile_options(pt_core PRIVATE -Wall -Wextra -Wpedantic)

add_executable(pt_denoise src/main.cpp)
target_link_libraries(pt_denoise PRIVATE pt_core)
target_compile_options(pt_denoise PRIVATE -Wall -Wextra -Wpedantic)

include(CTest)
if(BUILD_TESTING)
  add_executable(pt_tests tests/unit_tests.cpp)
  target_link_libraries(pt_tests PRIVATE pt_core)
  target_compile_options(pt_tests PRIVATE -Wall -Wextra -Wpedantic)
  add_test(NAME pt_tests COMMAND pt_tests)
endif()

