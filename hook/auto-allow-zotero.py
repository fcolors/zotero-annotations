#!/usr/bin/env python3
"""
ZCode PreToolUse hook: auto-approve (allow) trusted read-only commands so they
skip the approval prompt, while every other command keeps the normal flow.

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

# Extend this list to auto-approve other trusted read-only commands.
# Each entry: (compiled regex matched against the Bash command string, reason)
# NOTE: the regex requires a python interpreter right before the script name,
# so commands like `cat zotero_annotations.py` are NOT auto-allowed.
#
# DELIBERATE NON-WHITELIST: the OpenAI zotero plugin helper
# (`.../zotero/scripts/zotero.py`) is intentionally NOT whitelisted. It is a
# different command, supports writes (import), and lives under a versioned
# plugin-cache path. The skill's strict workflow never needs it — status is
# checked inside zotero_annotations.py via /api/schema — so leaving it out keeps
# the whitelist narrow and the "no approval" guarantee honest.
#
# Environment: built & tested against ZCode v3.7.6 (the `decision` value schema,
# "approve"/"block", is pinned to that version). For other ZCode versions, verify
# the hook protocol on your local install and adjust accordingly.
ALLOW_PATTERNS = [
    (re.compile(r"python(?:3(?:\.\d+)?)?\s+[^\n;|&]*zotero_annotations\.py"),
     "Zotero 批注读取脚本（只读本地 API）"),
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
