import time
import requests

import json
import base64
import hmac
import hashlib
import urllib.parse


PUSH_METHOD = "DD"

# 钉钉 token
# 在群内添加机器人，获取机器人的 webhook 地址和签名，并将其填入 DD_BOT_TOKEN 和 DD_BOT_SECRET 中
DD_BOT_TOKEN = "c443d4b28d91876cb0d2a36e405b44c525e701e178f41445f09a468f4d453d4f"
DD_BOT_SECRET = "SEC991410be16a0e7156b6a015880d69768df8684a3be80bcd516c872eec032914e"


MESSAGE = "测试通知"

# 推送到钉钉
def dingtalk(text, desp, DD_BOT_TOKEN, DD_BOT_SECRET=None):
    url = f"https://oapi.dingtalk.com/robot/send?access_token={DD_BOT_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "msgtype": "text",
        "text": {
            "content": f"{text}\n{desp}"
        }
    }

    if DD_BOT_TOKEN and DD_BOT_SECRET:
        timestamp = str(round(time.time() * 1000))
        secret_enc = DD_BOT_SECRET.encode("utf-8")
        string_to_sign = f"{timestamp}\n{DD_BOT_SECRET}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(
            secret_enc, string_to_sign_enc, digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(
            base64.b64encode(hmac_code).decode("utf-8").strip()
        )
        url = f"{url}&timestamp={timestamp}&sign={sign}"

    response = requests.post(url, headers=headers, data=json.dumps(payload))

    try:
        data = response.json()
        print(data)
        # if response.status_code == 200 and data.get("errcode") == 0:
        #     print("info:    钉钉发送通知消息成功🎉")
        # else:
        #     print(f"error:  钉钉发送通知消息失败😞\n{data.get('errmsg')}")
    except Exception as e:
        print(f"error:  钉钉发送通知消息失败😞\n{e}")

    return response.json()

def send_message():
    if PUSH_METHOD == "DD":
        dingtalk("脚本执行通知", MESSAGE, DD_BOT_TOKEN, DD_BOT_SECRET)

send_message()
