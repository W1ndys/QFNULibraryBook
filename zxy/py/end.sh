#!/bin/bash
echo "============== $(date '+%Y-%m-%d %H:%M:%S') - Starting =============" >> /root/QFNU-Library-Book-main/py/end.log
/root/anaconda3/envs/lib/bin/python /root/QFNU-Library-Book-main/py/sign_out.py >> /root/QFNU-Library-Book-main/py/end.log 2>&1
echo "============== $(date '+%Y-%m-%d %H:%M:%S') - Finished =============" >> /root/QFNU-Library-Book-main/py/end.log
