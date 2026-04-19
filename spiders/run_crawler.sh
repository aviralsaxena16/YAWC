#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_crawler.sh  —  one-liner helper to launch the Reddit crawler in background
# Usage:  bash run_crawler.sh [subreddit] [max_posts] [hours]
# ─────────────────────────────────────────────────────────────────────────────

SUBREDDIT=${1:-"python"}    # default: r/python
MAX_POSTS=${2:-500}         # default: 500 posts
HOURS=${3:-24}              # default: 24 hr window

LOGFILE="logs/crawler_${SUBREDDIT}_$(date +%Y%m%d_%H%M%S).log"
mkdir -p logs output

echo "Starting crawler..."
echo "  Target  : r/${SUBREDDIT}"
echo "  Posts   : ${MAX_POSTS}"
echo "  Hours   : ${HOURS}"
echo "  Log     : ${LOGFILE}"

nohup python reddit_crawler.py \
    --target   "$SUBREDDIT"   \
    --posts    "$MAX_POSTS"   \
    --hours    "$HOURS"       \
    > "$LOGFILE" 2>&1 &

PID=$!
echo ""
echo "✅ Crawler running in background with PID ${PID}"
echo ""
echo "Useful commands:"
echo "  tail -f ${LOGFILE}          # live log"
echo "  kill ${PID}                 # graceful stop (progress saved)"
echo "  wc -l output/${SUBREDDIT}_posts.jsonl   # count saved posts"
