#!/bin/bash
# Reassemble llamafile from split parts
# Run this after cloning the repo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "llamafile" ]; then
    echo "✅ llamafile already assembled"
    exit 0
fi

echo "🔧 Assembling llamafile from parts..."

if [ ! -f "llamafile.part.aa" ]; then
    echo "❌ llamafile parts not found"
    exit 1
fi

cat llamafile.part.* > llamafile
chmod +x llamafile

echo "✅ llamafile assembled ($(du -h llamafile | cut -f1))"
echo "   Location: $SCRIPT_DIR/llamafile"
