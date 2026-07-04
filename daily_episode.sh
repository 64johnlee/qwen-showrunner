#!/bin/bash
# Daily episode: Qwen invents today's premise (genre rotates by weekday),
# the showrunner renders it, and the finished mp4 lands in the Windows
# Videos folder. Scheduled from Windows Task Scheduler via:
#   wsl.exe -u user bash -lc /home/user/qwen-showrunner/daily_episode.sh
set -euo pipefail
cd /home/user/qwen-showrunner
mkdir -p logs
LOG="logs/daily-$(date +%F).log"
exec >> "$LOG" 2>&1

echo "=== $(date '+%F %T') daily episode start ==="
PREMISE=$(python3 daily_premise.py)
echo "premise: $PREMISE"

python3 run.py "$PREMISE" --lang zh --sub-lang en --shots 10

EP_DIR=$(ls -td output/episode-* | head -1)
TITLE=$(python3 -c "import json;print(json.load(open('$EP_DIR/script.json'))['title'])")
DEST="/mnt/c/Users/User/Videos/短剧_$(date +%m%d)_${TITLE}.mp4"
cp "$EP_DIR/episode.mp4" "$DEST"
echo "=== done -> $DEST ==="
