CXX ?= g++
CXXFLAGS ?= -std=c++20 -O3 -Wall -Wextra -Wpedantic
PIXEL_SAMPLES ?= 131072
FLUX_SAMPLES ?= 2000000
PENUMBRA_SAMPLES ?= 131072

.PHONY: all verify clean

all: verify

build/area_lights: src/area_lights.cpp
	@mkdir -p build
	$(CXX) $(CXXFLAGS) $< -o $@

verify: build/area_lights
	python3 scripts/verify.py \
		--binary build/area_lights \
		--pixel-samples $(PIXEL_SAMPLES) \
		--flux-samples $(FLUX_SAMPLES) \
		--penumbra-samples $(PENUMBRA_SAMPLES)

clean:
	python3 -c "import shutil; shutil.rmtree('build', ignore_errors=True)"
