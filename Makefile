# Makefile — EPYC 7452 (znver2) native build, no external deps.
CC      ?= gcc
CFLAGS  ?= -O3 -march=znver2 -mtune=znver2 -flto -fno-math-errno -funroll-loops -Wall
LDFLAGS ?= -flto

probe: probe.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o probe probe.c

# aggressive profile-guided option (optional, best-in-class on this silicon)
probe-pgo: probe.c
	$(CC) $(CFLAGS) -fprofile-generate -o probe.gen probe.c
	./probe.gen < /dev/null > /dev/null
	$(CC) $(CFLAGS) -fprofile-use -o probe probe.c

clean:
	rm -f probe probe.gen *.gcda *.gcno

.PHONY: clean
