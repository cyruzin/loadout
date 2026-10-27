#!/usr/bin/env bash
# Builds the frontend and writes out/Loadout.zip (a Loadout/ folder, the layout Decky installs).
set -euo pipefail
cd "$(dirname "$0")/.."

pnpm run build
rm -rf out
mkdir -p out/Loadout
cp -r plugin.json package.json main.py LICENSE README.md dist py_modules out/Loadout/
mkdir out/Loadout/scripts && cp scripts/capture.py out/Loadout/scripts/  # for contributors, on the device
find out -name __pycache__ -prune -exec rm -rf {} +
(cd out && zip -qr Loadout.zip Loadout)
echo "out/Loadout.zip ($(node -p 'require("./package.json").version'))"
