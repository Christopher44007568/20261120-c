CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wpedantic -Wshadow -Wconversion

SRC := src/main.cpp src/trail.cpp src/rasterizer.cpp src/material_graph.cpp
OBJ := $(SRC:.cpp=.o)

all: build/trail_demo

build:
	mkdir -p build artifacts

build/trail_demo: $(OBJ) | build
	$(CXX) $(CXXFLAGS) -o $@ $(OBJ)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

run: build/trail_demo
	./build/trail_demo

clean:
	rm -rf build

.PHONY: all run clean
