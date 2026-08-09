#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

got="$("${script_dir}/hello.sh")"
[[ "${got}" == "Hello, World!" ]] || { echo "FAIL: default arg -- got '${got}'" >&2; exit 1; }

got="$("${script_dir}/hello.sh" Claude)"
[[ "${got}" == "Hello, Claude!" ]] || { echo "FAIL: named arg -- got '${got}'" >&2; exit 1; }

echo "PASS: 2/2"
