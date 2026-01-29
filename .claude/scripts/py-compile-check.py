#!/usr/bin/env python3
"""PostToolUse hook: Check Python file syntax after Edit/Write.

Receives JSON via stdin from Claude Code with tool_input.file_path.
Only checks .py files. Returns exit code 2 with error message on syntax errors.
"""
import json
import sys
import subprocess

try:
    data = json.load(sys.stdin)
    file_path = data.get('tool_input', {}).get('file_path', '')

    if not file_path.endswith('.py'):
        sys.exit(0)

    result = subprocess.run(
        [sys.executable, '-m', 'py_compile', file_path],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        print(f'[Hook] Python 語法錯誤，請修正: {error_msg}', file=sys.stderr)
        sys.exit(2)

except Exception:
    sys.exit(0)
