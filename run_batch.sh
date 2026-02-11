#!/bin/bash
# Batch process all "Module N Part X" videos
# Outputs each translated video next to the original

set -e

BASE="c:/Users/rcox/INSULATIONS, INC/Supervisory Training - Documents"
PROJECT="C:/Users/rcox/elevenlabs-n8n"

cd "$PROJECT"

# Find all matching videos and process them
find "$BASE" -type f -name "*.mp4" | grep -iE "Module [0-9]+ Part" | sort | while IFS= read -r video; do
    dir=$(dirname "$video")
    echo ""
    echo "========================================"
    echo "Processing: $(basename "$video")"
    echo "Output to: $dir"
    echo "========================================"

    python -m video_translator.cli "$video" --output-dir "$dir" --yes --keep-intermediates --verbose 2>&1

    echo "Finished: $(basename "$video")"
    echo ""
done

echo ""
echo "All videos processed!"
