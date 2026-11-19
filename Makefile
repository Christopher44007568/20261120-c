CXX ?= g++
CXXFLAGS ?= -O3 -std=c++20 -Wall -Wextra -Wpedantic
LDFLAGS ?= -pthread

TARGET := rpt
SOURCES := src/main.cpp

.PHONY: all clean test

all: $(TARGET)

$(TARGET): $(SOURCES) src/vec.h src/scene.h src/scenes.h src/camera.h \
	src/shading.h src/integrators.h src/bdpt.h src/renderer.h
	$(CXX) $(CXXFLAGS) $(SOURCES) -o $@ $(LDFLAGS)

test: $(TARGET)
	python3 tests/smoke.py

clean:
	rm -f $(TARGET)
