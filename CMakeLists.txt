cmake_minimum_required(VERSION 3.20)
project(visibility_buffer_bench LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(visbuf_bench_lib
    src/scene.cpp
    src/pipeline.cpp
    src/benchmark.cpp
)
target_include_directories(visbuf_bench_lib PUBLIC src)
target_compile_options(visbuf_bench_lib PRIVATE
    -Wall -Wextra -Wpedantic -O3
)

add_executable(visbuf_bench src/main.cpp)
target_link_libraries(visbuf_bench PRIVATE visbuf_bench_lib)
target_compile_options(visbuf_bench PRIVATE
    -Wall -Wextra -Wpedantic -O3
)

enable_testing()
add_test(NAME benchmark_self_test COMMAND visbuf_bench --self-test)
