"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const hello_1 = require("./hello");
function assertEqual(actual, expected, label) {
    if (actual !== expected) {
        console.error(`FAIL: ${label} -- got '${actual}', expected '${expected}'`);
        process.exit(1);
    }
}
assertEqual((0, hello_1.greet)("World"), "Hello, World!", "default-style greeting");
assertEqual((0, hello_1.greet)("Claude"), "Hello, Claude!", "named greeting");
console.log("PASS: 2/2");
