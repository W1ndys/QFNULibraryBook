#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="$(dirname "$SCRIPT_DIR")/py"
LOG_FILE="$SCRIPT_DIR/logs/get_seat_$(date +\%Y\%m\%d).log"

mkdir -p "$SCRIPT_DIR/logs"

cd "$PYTHON_DIR" || exit 1

{
    echo "========== $(date) 开始执行 get_seat.py =========="
    python3 get_seat.py
    echo "========== $(date) get_seat.py 执行完成 =========="
} 2>&1 | tee -a "$LOG_FILE"