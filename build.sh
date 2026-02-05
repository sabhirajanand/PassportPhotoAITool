#!/usr/bin/env bash
# Build standalone PassportPhotoCreator (no Python needed to run).
# Requires: pip install -r requirements.txt pyinstaller

set -e
cd "$(dirname "$0")"

echo "Installing build dependency..."
pip install pyinstaller -q

echo "Building standalone app..."
pyinstaller PassportPhotoCreator.spec

echo "Done. Run the app:"
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  open dist/PassportPhotoCreator/PassportPhotoCreator"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    echo "  dist\\PassportPhotoCreator\\PassportPhotoCreator.exe"
else
    echo "  dist/PassportPhotoCreator/PassportPhotoCreator"
fi
