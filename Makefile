.PHONY: all run test clean

BUILD_DIR ?= build
OUTPUT_DIR ?= outputs

all:
	cmake -S . -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=Release
	cmake --build $(BUILD_DIR) -j

run: all
	./$(BUILD_DIR)/ibl_demo --output $(OUTPUT_DIR)
	python3 tools/report.py --input $(OUTPUT_DIR) --output $(OUTPUT_DIR)

test: all
	ctest --test-dir $(BUILD_DIR) --output-on-failure

clean:
	rm -rf $(BUILD_DIR)$(if $(OUTPUT_DIR), $(OUTPUT_DIR))
