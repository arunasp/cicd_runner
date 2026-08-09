export function greet(name: string): string {
    return `Hello, ${name}!`;
}

function main(): void {
    const name = process.argv[2] ?? "World";
    console.log(greet(name));
}

if (require.main === module) {
    main();
}
