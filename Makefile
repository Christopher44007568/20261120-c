CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra

.PHONY: all run clean

all: build/gi build/terrain

build/gi: src/main.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $<

build/terrain: src/terrain.cpp
	mkdir -p build
	$(CXX) $(CXXFLAGS) -o $@ $<

run: all
	mkdir -p artifacts/raw
	./build/gi artifacts/raw
	./build/terrain artifacts/raw 350
	python3 tools/make_report.py

clean:
	rm -rf build
