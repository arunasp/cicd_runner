import { greet } from "./hello";

function assertEqual(actual: string, expected: string, label: string): void {
    if (actual !== expected) {
        console.error(`FAIL: ${label} -- got '${actual}', expected '${expected}'`);
        process.exit(1);
    }
}

assertEqual(greet("World"), "Hello, World!", "default-style greeting");
assertEqual(greet("Claude"), "Hello, Claude!", "named greeting");
console.log("PASS: 2/2");
