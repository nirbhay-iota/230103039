#!/usr/bin/env python3
"""List the placeholders [[MEASURE...]] still left in the report, with their line numbers."""
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "report/report.md")
open_items = [(n, m.group(0)) for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
              for m in re.finditer(r"\[\[MEASURE[^\]]*\]\]|NAME, roll number ROLL_NUMBER", line)]
for n, text in open_items:
    print(f"{path}:{n}: {text}")
print(f"{len(open_items)} placeholders left")
sys.exit(1 if open_items else 0)
