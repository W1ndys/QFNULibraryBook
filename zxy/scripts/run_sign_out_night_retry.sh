#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_DIR="$(dirname "$SCRIPT_DIR")/py"
LOG_FILE="$SCRIPT_DIR/logs/sign_out_night_cron_$(date +\%Y\%m\%d).log"

mkdir -p "$SCRIPT_DIR/logs"

cd "$PYTHON_DIR" || exit 1

MAX_RETRIES=2000
RETRY_COUNT=0
SUCCESS=false
ALREADY_SIGNED_OUT=false

{
    echo "========== $(date) 开始执行 sign_out.py 晚间签退 (重试模式) =========="

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        echo "$(date) 第 $((RETRY_COUNT + 1)) 次尝试执行 sign_out.py"

        python3 sign_out.py
        EXIT_CODE=$?

        if [ $EXIT_CODE -eq 0 ]; then
            echo "$(date) sign_out.py 执行成功"
            SUCCESS=true
            break
        else
            # 检查是否是"已经签退"的情况（通过日志判断）
            if grep -q "已经签退\|没有找到正在使用的座位" "$LOG_FILE" 2>/dev/null; then
                echo "$(date) 检测到已签退，不作为失败处理"
                ALREADY_SIGNED_OUT=true
                break
            fi

            RETRY_COUNT=$((RETRY_COUNT + 1))
            echo "$(date) 执行失败，exit code: $EXIT_CODE，已重试: $RETRY_COUNT/$MAX_RETRIES"
            sleep 1
        fi
    done

    if [ "$ALREADY_SIGNED_OUT" = true ]; then
        echo "$(date) 已签退，跳过"
    elif [ "$SUCCESS" = false ]; then
        echo "$(date) 达到最大重试次数 ($MAX_RETRIES)，执行失败"
    fi

    echo "========== $(date) sign_out.py 晚间签退 (重试模式) 执行结束 =========="
} 2>&1 | tee -a "$LOG_FILE"