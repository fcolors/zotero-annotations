#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

rm -f zotero-pdf-bridge.xpi

zip -9 zotero-pdf-bridge.xpi \
  manifest.json \
  bootstrap.js

printf '%s\n' "built: zotero-pdf-bridge.xpi"
