"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.greet = greet;
function greet(name) {
    return `Hello, ${name}!`;
}
function main() {
    const name = process.argv[2] ?? "World";
    console.log(greet(name));
}
if (require.main === module) {
    main();
}
