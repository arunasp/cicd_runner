#include <stdio.h>
#include "greet.h"

const char *greet(const char *name) {
    static char buf[256];
    snprintf(buf, sizeof(buf), "Hello, %s!", name);
    return buf;
}
