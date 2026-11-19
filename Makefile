CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -flto
SRC := src/main.cpp src/raster.cpp
BIN := build/tile_rast

.PHONY: all clean run test

all: $(BIN)

$(BIN): $(SRC) src/raster.h
	@mkdir -p build
	$(CXX) $(CXXFLAGS) $(SRC) -o $(BIN)

run: all
	./scripts/run_benchmarks.sh

test: all
	$(CXX) $(CXXFLAGS) tests/selftest.cpp src/raster.cpp -o build/selftest
	./build/selftest

clean:
	rm -rf build results
