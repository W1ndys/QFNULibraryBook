#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="$(dirname "$SCRIPT_DIR")/py"
LOG_FILE="$SCRIPT_DIR/logs/get_seat_cron_$(date +\%Y\%m\%d).log"

mkdir -p "$SCRIPT_DIR/logs"

cd "$PYTHON_DIR" || exit 1

MAX_RETRIES=2000
RETRY_COUNT=0
SUCCESS=false

{
    echo "========== $(date) 开始执行 get_seat.py (重试模式) =========="

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        echo "$(date) 第 $((RETRY_COUNT + 1)) 次尝试执行 get_seat.py"

        python3 get_seat.py
        EXIT_CODE=$?

        if [ $EXIT_CODE -eq 0 ]; then
            echo "$(date) get_seat.py 执行成功"
            SUCCESS=true
            break
        else
            RETRY_COUNT=$((RETRY_COUNT + 1))
            echo "$(date) 执行失败，exit code: $EXIT_CODE，已重试: $RETRY_COUNT/$MAX_RETRIES"
            sleep 1
        fi
    done

    if [ "$SUCCESS" = false ]; then
        echo "$(date) 达到最大重试次数 ($MAX_RETRIES)，执行失败"
    fi

    echo "========== $(date) get_seat.py (重试模式) 执行结束 =========="
} 2>&1 | tee -a "$LOG_FILE"