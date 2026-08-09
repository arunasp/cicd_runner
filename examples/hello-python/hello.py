#!/usr/bin/env python3
"""Real, filled-in "hello world" example for the standard CI/CD
pipeline vocabulary -- see ../project-skeleton/."""
import sys


def greet(name: str) -> str:
    return f"Hello, {name}!"


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "World"
    print(greet(name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
