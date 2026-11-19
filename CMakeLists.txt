cmake_minimum_required(VERSION 3.20)
project(hzb_cull_bench LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(hzb_cull
    src/main.cpp
    src/gl_context.cpp
    src/scene.cpp
    src/hzb_benchmark.cpp
    src/turbulence.cpp
)

target_include_directories(hzb_cull PRIVATE src)
target_compile_options(hzb_cull PRIVATE -Wall -Wextra -Wpedantic)
target_link_libraries(hzb_cull PRIVATE dl)

enable_testing()
add_test(NAME hzb_benchmark COMMAND hzb_cull --assert --frames 7)
set_tests_properties(hzb_benchmark PROPERTIES TIMEOUT 180)
set_tests_properties(hzb_benchmark PROPERTIES
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
