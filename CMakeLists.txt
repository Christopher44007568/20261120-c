cmake_minimum_required(VERSION 3.16)
project(ibl_importance_sampling LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

add_executable(ibl_demo
  src/env_map.cpp
  src/sampler.cpp
  src/render.cpp
  src/io.cpp
  src/main.cpp
)
target_include_directories(ibl_demo PRIVATE include)
target_compile_options(ibl_demo PRIVATE -Wall -Wextra -Wpedantic)

enable_testing()
add_executable(ibl_tests
  tests/test_ibl.cpp
  src/env_map.cpp
  src/sampler.cpp
  src/render.cpp
)
target_include_directories(ibl_tests PRIVATE include)
target_compile_options(ibl_tests PRIVATE -Wall -Wextra -Wpedantic)
add_test(NAME ibl_tests COMMAND ibl_tests)
