CC ?= cc
CFLAGS ?= -O3 -std=c11 -Wall -Wextra -Wpedantic -Werror
CPPFLAGS := -Iinclude
LDLIBS := -lm
BUILD := build
ARTIFACTS := artifacts

CLI_SRC := src/curl_noise.c src/layout.c src/experiment.c src/main.c
LIB_SRC := src/curl_noise.c src/layout.c
CLI_OBJ := $(CLI_SRC:src/%.c=$(BUILD)/%.o)
LIB_OBJ := $(LIB_SRC:src/%.c=$(BUILD)/lib/%.o)

.PHONY: all check run clean

all: $(BUILD)/curl_noise $(BUILD)/libcurlnoise.so

$(BUILD)/curl_noise: $(CLI_OBJ)
	$(CC) $(CFLAGS) $(LDFLAGS) $^ -o $@ $(LDLIBS)

$(BUILD)/libcurlnoise.so: $(LIB_OBJ)
	$(CC) -shared $(CFLAGS) $(LDFLAGS) $^ -o $@ $(LDLIBS)

$(BUILD)/%.o: src/%.c include/curl_noise.h | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

$(BUILD)/lib/%.o: src/%.c include/curl_noise.h | $(BUILD)/lib
	$(CC) $(CPPFLAGS) $(CFLAGS) -fPIC -c $< -o $@

$(CLI_OBJ): src/experiment.h

$(BUILD) $(BUILD)/lib:
	mkdir -p $@

run: all
	$(BUILD)/curl_noise --out $(ARTIFACTS)

check: all
	$(BUILD)/curl_noise --out $(ARTIFACTS)
	$(BUILD)/curl_noise --layout-json $(ARTIFACTS)/layout_c.json
	python3 tools/render.py $(ARTIFACTS)
	python3 bindings/curl_noise.py --layout-json $(ARTIFACTS)/layout_python.json
	python3 tests/run_checks.py $(ARTIFACTS)

clean:
	rm -rf $(BUILD)
