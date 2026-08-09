#include <stdio.h>
#include "greet.h"

int main(int argc, char *argv[]) {
    const char *name = argc > 1 ? argv[1] : "World";
    printf("%s\n", greet(name));
    return 0;
}
