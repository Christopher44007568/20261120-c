CC = gcc
CFLAGS = -O2 -Wall -Wextra -std=c11
LDLIBS = -lm

all: clouds earlyz

clouds: src/main.c src/render.c src/cloud.c src/noise.c src/pngw.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

earlyz: src/earlyz.c
	$(CC) $(CFLAGS) -o $@ $^ $(LDLIBS)

clean:
	rm -f clouds earlyz

.PHONY: all clean
