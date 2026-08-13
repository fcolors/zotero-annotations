#!/usr/bin/env python3
"""
ZCode PreToolUse hook: auto-approve (allow) the packaged CLI executable
zotero_annotations_cli (Windows: zotero_annotations_cli.exe) for ANY
invocation, so it always skips the approval prompt.

The CLI is fully read-only: it only sends GET requests to the Zotero local API
(port 23119) and, in context mode, reads the user's own local PDF files
(never writes, never modifies, never downloads). Because every flag
combination is safe, we approve the whole executable regardless of arguments.

IMPORTANT — this hook targets the EXECUTABLE, not the python script:
  * Packaged/distributed form (the normal runtime for end users):
      zotero_annotations_cli.exe --key AAAA0000
      ./zotero_annotations_cli --key AAAA0000
      C:\\path\\to\\dist\\zotero_annotations_cli\\zotero_annotations_cli.exe ...
  * It does NOT match `python3 .../zotero_annotations_cli.py ...` — during
    development you run the .py directly, and that invocation is NOT
    auto-allowed here (you can add it, or use the sibling skill
    zotero-annotations whose hook matches its own .py).

Reads hook JSON from stdin (fields: tool_name, tool_input.command, ...).
  - If a Bash command matches an ALLOW_PATTERNS entry
        -> print {"decision":"approve"} and exit 0  (ZCode skips the prompt)
  - otherwise -> exit 0 silently (normal approval flow continues)

NOTE on the decision value: ZCode (v3.7.6) parses hook stdout with a strict
schema where top-level `decision` accepts only {"approve","block"} — "approve"
maps to permission-allow. `"allow"` is NOT in the enum and fails validation,
silently dropping the hook result (log: hook.run.failed) so the prompt still
appears. Use "approve" for allow, "block" for deny. (Alternative: return
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}
for the same effect.)

Security note: approving the whole executable relies on the CLI staying
read-only. If you later add any flag that writes/mutates data, restrict the
pattern again.

Environment: built & tested against ZCode v3.7.6 (the `decision` value schema,
"approve"/"block", is pinned to that version). For other ZCode versions, verify
the hook protocol (decision values, PreToolUse event fields) on your local
install and adjust accordingly; cross-version compatibility is not guaranteed.

Install: register under hooks.events.PreToolUse in
  ~/.zcode/cli/config.json  (user)  or  <repo>/.zcode/config.json  (workspace)
and make sure "hooks": { "enabled": true, ... }. See README.md of this repo.

If you already have another PreToolUse hook (e.g. a sensitive-path blocker),
prefer MERGING this allow-list into that same script so there is a single
decision point, avoiding ambiguity when multiple hooks return decisions.
"""

import json
import re
import sys

# Match the packaged executable ONLY as the command itself (the token right
# after a command boundary), not as an argument to another tool. Allows:
#   - a multi-level path prefix: C:\...\dist\...\ , .\dist\...\ , /opt/.../
#   - a chained-command prefix: `cd dist && zotero_annotations_cli.exe ...`
# The name must be `zotero_annotations_cli` (+ optional `.exe`) and be followed
# by whitespace or end-of-line. Commands where the CLI is NOT the command
# itself are not matched: `python3 ...zotero_annotations_cli.py`,
# `cat ...zotero_annotations_cli.py`, `vim ...zotero_annotations_cli.exe`,
# `echo zotero_annotations_cli.exe`.
ALLOW_PATTERNS = [
    (re.compile(
        r"(?:^|(?:[;|&]|&&)\s*)"
        r"(?:[^\s;|&]*[\\/])*"
        r"zotero_annotations_cli(?:\.exe)?(?=\s|$)"
     ),
     "Zotero 批注 CLI 可执行文件（只读：本地 API 元数据 + 本地 PDF 原文，安全）"),
]


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)  # nothing to check -> pass through

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)  # malformed input: fail open, never break a session

    tool_name = data.get("tool_name") or data.get("toolName") or ""
    tool_input = data.get("tool_input") or data.get("toolInput") or {}

    if tool_name != "Bash":
        sys.exit(0)

    commands = []
    v = tool_input.get("command")
    if isinstance(v, str):
        commands.append(v)
    elif isinstance(v, list):
        commands.extend(x for x in v if isinstance(x, str))

    for cmd in commands:
        for pattern, reason in ALLOW_PATTERNS:
            if pattern.search(cmd):
                # Explicit allow decision -> ZCode skips the approval prompt.
                # value MUST be "approve" (schema enum: approve/block), not "allow".
                print(json.dumps({
                    "decision": "approve",
                    "reason": "已自动放行: %s" % reason,
                }))
                sys.exit(0)

    sys.exit(0)  # no decision -> normal flow


if __name__ == "__main__":
    main()
