CXX ?= g++
CXXFLAGS := -std=c++20 -O3 -march=native -pthread

BINS := frustum_cull offset_shell

.PHONY: all clean bench shell

all: $(BINS)

frustum_cull: src/frustum_cull.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

offset_shell: src/offset_shell.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

# 1,000,000 instances, 60 timed rounds per thread count.
bench: frustum_cull
	./frustum_cull 1000000 60

# SDF offset-shell volume / watertightness / self-intersection report.
shell: offset_shell
	./offset_shell 150 | tee artifacts/offset_shell_report.txt

# Export representative meshes and verify them independently from the OBJ.
obj: offset_shell
	./offset_shell 90 obj
	python3 tools/check_obj.py artifacts/*.obj

clean:
	rm -f $(BINS)
