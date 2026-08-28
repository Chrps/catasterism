#!/usr/bin/env python3
"""Compile every GLSL string in the client with glslang.

Shaders only fail at runtime otherwise, and a runtime shader failure renders a
black screen with no obvious cause. Cheap to check, so check it.

    docker run --rm -v "$PWD:/w" -w /w debian:bookworm-slim bash -c \
      'apt-get update -qq && apt-get install -y -qq glslang-tools python3 && \
       python3 tools/validate_shaders.py'
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "client/src/shaders.ts"
STAGE_SUFFIX = {"VERTEX": "vert", "FRAGMENT": "frag"}


def main() -> int:
    if not shutil.which("glslangValidator"):
        print("glslangValidator not installed; skipping", file=sys.stderr)
        return 0

    text = SOURCE.read_text()
    shaders = re.findall(r"export const (\w+) = /\* glsl \*/ `(.*?)`;", text, re.S)
    if not shaders:
        print(f"no shaders found in {SOURCE}", file=sys.stderr)
        return 1

    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in shaders:
            stage = next((v for k, v in STAGE_SUFFIX.items() if name.endswith(k)), None)
            if stage is None:
                print(f"  {name}: cannot infer stage from the name", file=sys.stderr)
                failures += 1
                continue
            path = Path(tmp) / f"{name.lower()}.{stage}"
            path.write_text(body)
            result = subprocess.run(
                ["glslangValidator", str(path)], capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  {name:20} OK")
            else:
                failures += 1
                print(f"  {name:20} FAIL")
                print("\n".join("      " + l for l in result.stdout.splitlines()))
    print(f"\n{len(shaders) - failures}/{len(shaders)} shaders compile")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
