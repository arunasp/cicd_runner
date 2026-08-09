# Real, filled-in "hello world" example -- not a stub. Demonstrates
# the standard lint/test/build/deploy/verify/e2e/all target
# vocabulary (see ../project-skeleton/) with real gcc compilation.
# Split into greet.c (library function) + main.c (entry point) so
# test.c can link against greet.c without a duplicate-main conflict
# -- the standard way to make C code testable at all.
-include ../cicd-common.mk
-include /etc/cicd-common.mk

CC ?= gcc
CFLAGS ?= -Wall -Wextra -Wpedantic -std=c11
PREFIX ?= /usr/local

.PHONY: lint test build deploy verify e2e all clean

# -Wall -Wextra -Wpedantic -Werror -fsyntax-only IS a genuine lint
# pass for C -- no separate linter needed for this small an example.
lint: ## Static checks (gcc -Wall -Wextra -Wpedantic -Werror)
	$(CC) $(CFLAGS) -Werror -fsyntax-only greet.c main.c

build: hello ## Compile the binary

hello: greet.c main.c greet.h
	$(CC) $(CFLAGS) -o hello greet.c main.c

test_hello: greet.c test.c greet.h
	$(CC) $(CFLAGS) -o test_hello greet.c test.c

test: test_hello ## Unit tests
	./test_hello

deploy: build ## Install the binary to PREFIX/bin
	install -d $(PREFIX)/bin
	install -m 755 hello $(PREFIX)/bin/hello-gcc-example

verify: build ## Confirm the deployed binary actually works
	@got=$$(./hello); \
	if [ "$$got" != "Hello, World!" ]; then \
		echo "FAIL: got '$$got'" >&2; exit 1; \
	fi; \
	echo "PASS: verify"

e2e: verify ## Alias for verify

all: lint test build deploy verify ## Run the full pipeline

clean: ## Remove build artifacts
	rm -f hello test_hello
