#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "greet.h"

int main(void) {
    assert(strcmp(greet("World"), "Hello, World!") == 0);
    assert(strcmp(greet("Claude"), "Hello, Claude!") == 0);
    printf("PASS: 2/2\n");
    return 0;
}
