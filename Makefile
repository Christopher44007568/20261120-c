CXX ?= g++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra

raysort: src/main.cpp src/vec3.h src/cache_sim.h src/scene.h src/sort_key.h
	$(CXX) $(CXXFLAGS) -o $@ src/main.cpp

run: raysort
	./raysort

clean:
	rm -f raysort

.PHONY: run clean
