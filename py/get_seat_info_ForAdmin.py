import base64
import logging
import sys
import time
import datetime

import os
import yaml
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

import json

URL_GET_SEAT = "http://libyy.qfnu.edu.cn/api/Seat/confirm"
URL_CHECK_OUT = "http://libyy.qfnu.edu.cn/api/Space/checkout"
URL_CANCEL_SEAT = "http://libyy.qfnu.edu.cn/api/Space/cancel"

# 配置文件
CHANNEL_ID = ""
TELEGRAM_BOT_TOKEN = ""
CLASSROOMS_NAME = ""
SEAT_ID = ""
DATE = ""
USERNAME = ""
PASSWORD = ""
GITHUB = ""
BARK_URL = ""
BARK_EXTRA = ""
ANPUSH_TOKEN = ""
ANPUSH_CHANNEL = ""
DD_BOT_SECRET = ""
DD_BOT_TOKEN = ""
PUSH_METHOD = ""


# 读取YAML配置文件并设置全局变量
def read_config_from_yaml():
    global CHANNEL_ID, TELEGRAM_BOT_TOKEN, CLASSROOMS_NAME, SEAT_ID, DATE, USERNAME, PASSWORD, GITHUB, BARK_EXTRA, BARK_URL, ANPUSH_TOKEN, ANPUSH_CHANNEL, PUSH_METHOD, DD_BOT_TOKEN, DD_BOT_SECRET
    current_dir = os.path.dirname(os.path.abspath(__file__))  # 获取当前文件所在的目录的绝对路径
    config_file_path = os.path.join(current_dir, "config.yml")  # 将文件名与目录路径拼接起来
    with open(config_file_path, "r", encoding="utf-8") as yaml_file:  # 指定为UTF-8格式打开文件
        config = yaml.safe_load(yaml_file)
        CHANNEL_ID = config.get("CHANNEL_ID", "")
        TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN", "")
        CLASSROOMS_NAME = config.get("CLASSROOMS_NAME", [])  # 将 CLASSROOMS_NAME 读取为列表
        SEAT_ID = config.get("SEAT_ID", [])  # 将 SEAT_ID 读取为列表
        DATE = config.get("DATE", "")
        USERNAME = config.get("USERNAME", "")
        PASSWORD = config.get("PASSWORD", "")
        GITHUB = config.get("GITHUB", "")
        BARK_URL = config.get("BARK_URL", "")
        BARK_EXTRA = config.get("BARK_EXTRA", "")
        ANPUSH_TOKEN = config.get("ANPUSH_TOKEN", "")
        ANPUSH_CHANNEL = config.get("ANPUSH_CHANNEL", "")
        DD_BOT_TOKEN = config.get("DD_BOT_TOKEN", "")
        DD_BOT_SECRET = config.get("DD_BOT_SECRET", "")
        PUSH_METHOD = config.get("PUSH_METHOD", "")


# 在代码的顶部定义全局变量
FLAG = False
SEAT_RESULT = {}
USED_SEAT = []
MESSAGE = ""
AUTH_TOKEN = ""
NEW_DATE = ""
TOKEN_TIMESTAMP = None
TOKEN_EXPIRY_DELTA = datetime.timedelta(hours=1, minutes=30)

# 配置常量: 没有插座的座位ID
EXCLUDE_ID = {
    "7115","7120","7125","7130","7135","7140","7145","7150","7155","7160","7165","7170","7175","7180",
    "7185","7190","7241","7244","7247","7250","7253","7256","7259","7262","7291","7296","7301","7306",
    "7311","7316","7321","7326","7331","7336","7341","7346","7351","7356","7361","7366","7369","7372",
    "7375","7378","7381","7384","7387","7390","7417","7420","7423","7426","7429","7432","7435","7438",
    "7443","7448","7453","7458","7463","7468","7473","7478","7483","7488","7493","7498","7503","7508",
    "7513","7518","7569","7572","7575","7578","7581","7584","7587","7590","7761","7764","7767","7770",
    "7773","7776","7779","7782","7785","7788","7791","7794","7797","7800","7803","7806",
}
read_config_from_yaml()

#! 指定获取的指定教室
CLASSROOMS_NAME = ['西校区图书馆-二层自习室']
DATE = 'tomorrow'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("开始打印日志")
print('\n')

# 创建教室名称到 ID 的映射字典
classroom_id_mapping = {
    "西校区图书馆-二层自习室": 45,
    "西校区图书馆-三层自习室": 38,
    "西校区图书馆-四层自习室": 39,
    "西校区图书馆-五层自习室": 40,
    "西校区东辅楼-二层自习室": 41,
    "西校区东辅楼-三层自习室": 42,
    "东校区图书馆-三层电子阅览室": 21,
    "东校区图书馆-三层自习室01": 22,
    "东校区图书馆-三层自习室02": 23,
    "东校区图书馆-四层中文现刊室": 24,
    "综合楼-801自习室": 16,
    "综合楼-803自习室": 17,
    "综合楼-804自习室": 18,
    "综合楼-805自习室": 19,
    "综合楼-806自习室": 20,
    "行政楼-四层东区自习室": 13,
    "行政楼-四层中区自习室": 14,
    "行政楼-四层西区自习室": 15,
    "电视台楼-二层自习室": 12,
}

# 常量定义
URL_CLASSROOM_DETAIL_INFO = "http://libyy.qfnu.edu.cn/api/Seat/date"
URL_CLASSROOM_SEAT = "http://libyy.qfnu.edu.cn/api/Seat/seat"
URL_CHECK_STATUS = "http://libyy.qfnu.edu.cn/api/Member/seat"

MAX_RETRIES = 100  # 最大重试次数
RETRY_DELAY = 3  # 重试间隔时间(秒)


# 获取预约的日期
def get_date(date):
    try:
        # 判断预约的时间
        if date == "today":
            nowday = datetime.datetime.now().date()
        elif date == "tomorrow":
            nowday = datetime.datetime.now().date() + datetime.timedelta(days=1)
        else:
            logger.error(f"未知的参数: {date}")
            sys.exit()
        # 结果判断
        if nowday:
            # logger.info(f"获取的日期: {nowday}")
            return nowday.strftime("%Y-%m-%d")  # 将日期对象转换为字符串
        else:
            logger.error("日期获取失败")
            sys.exit()

    except Exception as e:
        logger.error(f"获取日期异常: {str(e)}")
        sys.exit()


# 发送 post 请求并记录回复
def send_post_request_and_save_response(url, data, headers):
    retries = 0
    while retries < MAX_RETRIES:
        try:
            response = requests.post(url, json=data, headers=headers, timeout=120)
            response.raise_for_status()
            response_data = response.json()
            return response_data
        except requests.exceptions.Timeout:
            logger.error("请求超时，正在重试...")
            retries += 1
            time.sleep(RETRY_DELAY)
        except Exception as e:
            logger.error(f"request请求异常: {str(e)}")
            retries += 1
            time.sleep(RETRY_DELAY)
    logger.error("超过最大重试次数,请求失败。")
    sys.exit()


# 获取教室 id
def get_build_id(classname):
    build_id = classroom_id_mapping.get(classname)
    return build_id

# 获取日期 id
def get_segment(build_id, nowday):
    try:
        post_data = {"build_id": build_id}

        request_headers = {
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "Accept": "application/json, text/plain, */*",
            "lang": "zh",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
            "Origin": "http://libyy.qfnu.edu.cn",
            "Referer": "http://libyy.qfnu.edu.cn/h5/index.html",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,pl;q=0.5",
        }

        res = send_post_request_and_save_response(
            URL_CLASSROOM_DETAIL_INFO, post_data, request_headers
        )
        print(f'info:   response1: {res}')
        
        segment = None

        # 提取"今天"或者"明天"的教室的 segment
        for item in res["data"]:
            if item["day"] == nowday:
                segment = item["times"][0]["id"]
                break

        return segment
    except Exception as e:
        logger.error(f"获取segment时出错: {str(e)}")
        sys.exit()

"""{
    'code': 1, 
    'msg': '操作成功', 
    'data': [
        {
            'day': '2025-03-05', 
            'times': [
                {
                    'id': '1825731', 
                    'status': 1, 
                    'start': '10:56', 
                    'end': '22:00'
                }
            ]
        }, 
        {
            'day': '2025-03-06', 
            'times': [
                {
                    'id': '1825732', 
                    'status': 1, 
                    'start': '08:00', 
                    'end': '22:00'
                }
            ]
        }
    ]
}"""

# 根据当前系统时间获取 key
def get_key():
    # 获取当前日期，并转换为字符串
    current_date = datetime.datetime.now().strftime("%Y%m%d")

    # 生成回文
    palindrome = current_date[::-1]

    # 使用当前日期和回文作为密钥
    key = current_date + palindrome

    # print("当前日期:", current_date)
    # print("回文:", palindrome)
    # print("密钥:", key)

    return key


# 加密函数
def encrypt(text):
    # 自动获取 key
    key = get_key()
    # 目前获取到的加密密钥
    iv = "ZZWBKJ_ZHIHUAWEI"
    key_bytes = key.encode("utf-8")
    iv_bytes = iv.encode("utf-8")

    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    ciphertext_bytes = cipher.encrypt(pad(text.encode("utf-8"), AES.block_size))

    return base64.b64encode(ciphertext_bytes).decode("utf-8")


# 定义解密函数
def decrypt(ciphertext):
    # 自动获取 key
    key = get_key()
    # 目前获取到的加密密钥
    iv = "ZZWBKJ_ZHIHUAWEI"

    # 将密钥和初始化向量转换为 bytes 格式
    key_bytes = key.encode("utf-8")
    iv_bytes = iv.encode("utf-8")

    # 将密文进行 base64 解码
    ciphertext = base64.b64decode(ciphertext)

    # 使用 AES 进行解密
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    decrypted_bytes = cipher.decrypt(ciphertext)

    # 去除解密后的填充
    decrypted_text = unpad(decrypted_bytes, AES.block_size).decode("utf-8")

    return decrypted_text



# 获取教室的座位信息并寻找空闲座位
def get_seat_info(build_id, segment, nowday):
    try:
        interrupted = False
        while not interrupted:
            try:
                post_data = {
                    "area": build_id,
                    "segment": segment,
                    "day": nowday,
                    "startTime": "08:00",
                    "endTime": "22:00",
                }

                request_headers = {
                    "Content-Type": "application/json",
                    "Connection": "keep-alive",
                    "Accept": "application/json, text/plain, */*",
                    "lang": "zh",
                    "X-Requested-With": "XMLHttpRequest",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, "
                    "like Gecko)"
                    "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
                    "Origin": "http://libyy.qfnu.edu.cn",
                    "Referer": "http://libyy.qfnu.edu.cn/h5/index.html",
                    "Accept-Encoding": "gzip, deflate",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,pl;q=0.5",
                }

                res = send_post_request_and_save_response(
                    URL_CLASSROOM_SEAT, post_data, request_headers
                )
                # print(f'info:   response2: {res}')

                # 将 response 保存为 JSON 文件
                file_name = f"西校区图书馆-二层自习室.json"
                with open(file_name, "w", encoding="utf-8") as json_file:
                    json.dump(res, json_file, ensure_ascii=False, indent=4)
                print(f"info:   Response saved to {file_name}")

                # 寻找空闲座位
                free_seats = []
                for seat in res["data"]:
                    if seat["status_name"] == "空闲":
                        free_seats.append({"id": seat["id"], "no": seat["no"]})

                time.sleep(1)
                return free_seats

            except requests.exceptions.Timeout:
                logger.warning("请求超时，正在重试...")

            except Exception as e:
                logger.error(f"获取座位信息异常: {str(e)}")
                sys.exit()

            time.sleep(1)

    except KeyboardInterrupt:
        logger.info(f"主动停止程序")
    except Exception as e:
        logger.error(f"循环异常: {str(e)}")
        sys.exit()





# 选座主要逻辑
def select_seat(build_id, segment, nowday):
    global MESSAGE, FLAG
    retries = 0  # 添加重试计数器

    while not FLAG and retries < 1:  # 不断尝试获取座位
        print(f"info:   开始第 {retries+1} 次尝试获取座位")
        retries += 1

        # 获取空闲座位
        data = get_seat_info(build_id, segment, nowday)
        print(f'info:   空闲座位: {data}, {len(data)}')
        
        # if not data:
        #     logger.warning("获取座位信息失败，可能是时间段内不存在或该区域暂不可用")
        #     MESSAGE += "\n获取座位信息失败，可能是时间段内不存在或该区域暂不可用"
        #     send_message()
        #     sys.exit()
        # else:
        #     new_data = [d for d in data if d["id"] not in EXCLUDE_ID]
        #     if new_data:
        #         select_id = random_get_seat(new_data)
        #         logger.info(f"随机选择的座位为: {select_id}")
        #         post_to_get_seat(select_id, segment)
        #     else:
        #         time.sleep(3)
        #     continue


# 主函数
def get_info_and_select_seat():
    global AUTH_TOKEN, NEW_DATE, MESSAGE
    try:
        NEW_DATE = get_date(DATE)
        print(f'info:   预约日期: {NEW_DATE}')

        for i in CLASSROOMS_NAME:   # 遍历每个教室
            print(f"info:   预约教室名称: {CLASSROOMS_NAME}")
            
            # 获取教室 id
            build_id = get_build_id(i)
            print(f"info:   预约教室 ID: {build_id}")

            # 获取日期 id
            segment = get_segment(build_id, NEW_DATE)
            print(f'info:   segment: {segment}')

            # 选座
            select_seat(build_id, segment, NEW_DATE)

    except KeyboardInterrupt:
        logger.info("主动退出程序，程序将退出。")


get_info_and_select_seat()