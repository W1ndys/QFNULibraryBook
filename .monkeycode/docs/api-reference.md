# QFNU 图书馆预约系统 -- 接口文档

> 本文档基于 `py/` 目录下的代码整理，涵盖从登录认证到座位预约完成的全流程接口。
> 所有接口均为 HTTP 协议（非 HTTPS），基础域名如下：
>
> - IDS 统一认证系统：`http://ids.qfnu.edu.cn`
> - 图书馆预约系统：`http://libyy.qfnu.edu.cn`

---

## 目录

1. [全流程概览](#1-全流程概览)
2. [阶段一：IDS 统一认证登录](#2-阶段一ids-统一认证登录)
   - [2.1 获取登录页面（盐值 + execution）](#21-获取登录页面盐值--execution)
   - [2.2 检查是否需要验证码（可选）](#22-检查是否需要验证码可选)
   - [2.3 获取验证码图片（可选）](#23-获取验证码图片可选)
   - [2.4 提交 IDS 登录表单](#24-提交-ids-登录表单)
3. [阶段二：CAS 认证换取图书馆 Token](#3-阶段二cas-认证换取图书馆-token)
   - [3.1 IDS 重定向回调](#31-ids-重定向回调)
   - [3.2 获取 CAS Token](#32-获取-cas-token)
   - [3.3 用 CAS Token 换取 Bearer Token](#33-用-cas-token-换取-bearer-token)
4. [阶段三：获取预约所需信息](#4-阶段三获取预约所需信息)
   - [4.1 获取教室时间段信息（segment）](#41-获取教室时间段信息segment)
   - [4.2 获取教室座位列表](#42-获取教室座位列表)
5. [阶段四：提交座位预约](#5-阶段四提交座位预约)
   - [5.1 确认预约座位](#51-确认预约座位)
6. [阶段五：预约后操作](#6-阶段五预约后操作)
   - [6.1 查询个人座位状态](#61-查询个人座位状态)
   - [6.2 签到（扫码入座）](#62-签到扫码入座)
   - [6.3 签退（离座）](#63-签退离座)
   - [6.4 取消预约](#64-取消预约)
7. [附录](#7-附录)
   - [A. AES 加密算法说明](#a-aes-加密算法说明)
   - [B. IDS 密码加密算法说明](#b-ids-密码加密算法说明)
   - [C. 教室 ID 映射表](#c-教室-id-映射表)
   - [D. 预约状态码汇总](#d-预约状态码汇总)
   - [E. 通用请求头模板](#e-通用请求头模板)

---

## 1. 全流程概览

```
用户输入学号/密码
       |
       v
+-------------------------------+
| 阶段一：IDS 统一认证登录       |
|  1. GET  登录页 -> 获取盐值    |
|  2. POST 登录表单 -> 302重定向 |
+-------------------------------+
       |  Location 头包含回调 URL
       v
+-------------------------------+
| 阶段二：CAS 换取图书馆 Token   |
|  3. GET  IDS回调URL            |
|  4. GET  /api/cas/cas -> 302   |
|  5. POST /api/cas/user         |
|     -> 获取 Bearer Token       |
+-------------------------------+
       |  得到 "bearer{token}"
       v
+-------------------------------+
| 阶段三：获取预约所需信息       |
|  6. POST /api/Seat/date        |
|     -> 获取 segment            |
|  7. POST /api/Seat/seat        |
|     -> 获取空闲座位列表        |
+-------------------------------+
       |  选座策略（3种模式）
       v
+-------------------------------+
| 阶段四：提交座位预约           |
|  8. POST /api/Seat/confirm     |
|     -> 提交 AES 加密的预约数据 |
+-------------------------------+
       |  预约成功/失败
       v
+-------------------------------+
| 阶段五：预约后操作             |
|  9.  POST /api/Member/seat     |
|      -> 查询个人座位状态       |
|  10. POST /api/Seat/touch_qr.. |
|      -> 签到                   |
|  11. POST /api/Space/checkout  |
|      -> 签退                   |
|  12. POST /api/Space/cancel    |
|      -> 取消预约               |
+-------------------------------+
```

> **重要时间节点**：系统每天 **19:20** 开放次日座位预约。

---

## 2. 阶段一：IDS 统一认证登录

### 2.1 获取登录页面（盐值 + execution）

从 IDS 登录页 HTML 中提取密码加密所需的 `salt`（盐值）和 `execution`（CSRF Token）。

| 项目 | 值 |
|------|-----|
| **方法** | `GET` |
| **URL** | `http://ids.qfnu.edu.cn/authserver/login?service=http%3A%2F%2Flibyy.qfnu.edu.cn%2Fapi%2Fcas%2Fcas` |
| **需要 Cookie** | 否（首次请求，服务端会 Set-Cookie） |

**请求头**

| Header | 值 |
|--------|-----|
| User-Agent | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...` |
| Referer | `http://libyy.qfnu.edu.cn/` |

**响应**

- 状态码：`200 OK`
- Content-Type：`text/html`
- 关键 HTML 元素：
  - `<input id="pwdEncryptSalt" value="{salt}">` -- 密码加密盐值
  - `<input id="execution" value="{execution}">` -- 表单 CSRF Token
- 响应会设置 Session Cookie（如 `JSESSIONID`），后续请求必须携带

**代码位置**：`py/get_ids_token.py:15-32` (`get_salt_and_execution`)

---

### 2.2 检查是否需要验证码（可选）

检查当前账号是否需要输入验证码。当前代码中此步骤已被注释掉。

| 项目 | 值 |
|------|-----|
| **方法** | `GET` |
| **URL** | `http://ids.qfnu.edu.cn/authserver/checkNeedCaptcha.htl` |

**请求参数（Query String）**

| 参数 | 类型 | 说明 |
|------|------|------|
| `username` | string | 学号 |
| `_` | int | 当前时间戳（毫秒） |

**响应示例**

```json
{"isNeed": true}
```

**代码位置**：`py/get_ids_token.py:35-52` (`captcha_check`)

---

### 2.3 获取验证码图片（可选）

当需要验证码时，获取验证码图片。当前代码中此步骤已被注释掉。

| 项目 | 值 |
|------|-----|
| **方法** | `GET` |
| **URL** | `http://ids.qfnu.edu.cn/authserver/getCaptcha.htl?{timestamp_ms}` |

**响应**

- Content-Type：`image/jpeg` 或 `image/png`
- Body：验证码图片的二进制数据

**代码位置**：`py/get_ids_token.py:55-70` (`get_captcha`)

---

### 2.4 提交 IDS 登录表单

使用加密后的密码提交登录表单。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://ids.qfnu.edu.cn/authserver/login?service=http%3A%2F%2Flibyy.qfnu.edu.cn%2Fapi%2Fcas%2Fcas` |
| **Content-Type** | `application/x-www-form-urlencoded` |
| **需要 Cookie** | 是（步骤 2.1 获取的 Session Cookie） |

**请求体（Form Data）**

| 参数 | 类型 | 说明 |
|------|------|------|
| `username` | string | 学号 |
| `password` | string | AES 加密后的密码（见附录 B） |
| `captcha` | string | 验证码识别结果（不需要时为空字符串） |
| `_eventId` | string | 固定值 `submit` |
| `cllt` | string | 固定值 `userNameLogin` |
| `dllt` | string | 固定值 `generalLogin` |
| `lt` | string | 空字符串 |
| `execution` | string | 步骤 2.1 获取的 execution 值 |

**响应**

- 状态码：`302 Found`（登录成功）
- `Location` 头：重定向 URL，格式为 `http://libyy.qfnu.edu.cn/api/cas/cas?ticket=ST-XXXXX-XXXXX`
- **注意**：客户端在此步不自动跟随重定向（`allow_redirects=False`）

**代码位置**：`py/get_ids_token.py:73-117` (`get_token`)

---

## 3. 阶段二：CAS 认证换取图书馆 Token

### 3.1 IDS 重定向回调

访问步骤 2.4 返回的 `Location` URL（带 CAS ticket 的回调地址）。

| 项目 | 值 |
|------|-----|
| **方法** | `GET` |
| **URL** | 步骤 2.4 返回的 `Location` 值（含 ticket 参数） |
| **需要 Cookie** | 是（同一 Session） |

**响应**

- 状态码：`302 Found`
- 服务端验证 ticket 并设置图书馆系统的 Session Cookie
- **注意**：客户端在此步不自动跟随重定向（`allow_redirects=False`）

**代码位置**：`py/get_bearer_token.py:27`

---

### 3.2 获取 CAS Token

再次请求图书馆 CAS 接口，获取内部 CAS Token。

| 项目 | 值 |
|------|-----|
| **方法** | `GET` |
| **URL** | `http://libyy.qfnu.edu.cn/api/cas/cas` |
| **需要 Cookie** | 是（同一 Session） |

**响应**

- 状态码：`302 Found`
- `Location` 头末尾 32 个字符为 CAS Token
- 提取方式：`location_header[-32:]`

**代码位置**：`py/get_bearer_token.py:28-33`

---

### 3.3 用 CAS Token 换取 Bearer Token

将 CAS Token 发送到用户接口，换取最终的 Bearer Token。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://libyy.qfnu.edu.cn/api/cas/user` |
| **Content-Type** | `application/json` |

**请求体**

```json
{
  "cas": "<32位CAS Token>"
}
```

**响应示例**

```json
{
  "code": 1,
  "msg": "操作成功",
  "member": {
    "name": "张三",
    "token": "xxxxxxxxxxxxxxxxxxxxxx",
    ...
  }
}
```

**关键字段**

| 字段 | 说明 |
|------|------|
| `member.name` | 用户姓名 |
| `member.token` | Bearer Token（后续所有请求需携带） |

**Token 使用方式**：在后续请求的 `Authorization` 头中传入 `bearer{token}`（注意 bearer 和 token 之间无空格）。

**Token 有效期**：约 1.5 小时（代码中设置 `TOKEN_EXPIRY_DELTA = timedelta(hours=1, minutes=30)`）。

**代码位置**：`py/get_bearer_token.py:36-50`

---

## 4. 阶段三：获取预约所需信息

### 4.1 获取教室时间段信息（segment）

根据教室 ID（build_id）获取可预约的日期和时间段信息。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://libyy.qfnu.edu.cn/api/Seat/date` |
| **Content-Type** | `application/json` |

**请求体**

```json
{
  "build_id": 38
}
```

> `build_id` 为教室编号，完整映射见附录 C。

**响应示例**

```json
{
  "code": 1,
  "msg": "操作成功",
  "data": [
    {
      "day": "2026-04-18",
      "times": [
        {
          "id": 12345,
          "start": "08:00",
          "end": "22:00"
        }
      ]
    },
    {
      "day": "2026-04-19",
      "times": [
        {
          "id": 12346,
          "start": "08:00",
          "end": "22:00"
        }
      ]
    }
  ]
}
```

**关键字段**

| 字段 | 说明 |
|------|------|
| `data[].day` | 日期字符串，格式 `YYYY-MM-DD` |
| `data[].times[0].id` | 该日期对应的时间段 ID（即 segment），后续预约需要 |

**提取逻辑**：遍历 `data`，找到 `day` 与目标日期匹配的项，取其 `times[0].id` 作为 `segment`。

**代码位置**：`py/get_info.py:99-132` (`get_segment`)

---

### 4.2 获取教室座位列表

获取指定教室、指定日期和时间段的所有座位及其状态。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://libyy.qfnu.edu.cn/api/Seat/seat` |
| **Content-Type** | `application/json` |

**请求体**

```json
{
  "area": 38,
  "segment": 12346,
  "day": "2026-04-19",
  "startTime": "08:00",
  "endTime": "22:00"
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `area` | int | 教室 ID（即 build_id） |
| `segment` | int | 步骤 4.1 获取的时间段 ID |
| `day` | string | 目标日期，格式 `YYYY-MM-DD` |
| `startTime` | string | 起始时间，固定 `08:00` |
| `endTime` | string | 结束时间，固定 `22:00` |

**响应示例**

```json
{
  "code": 1,
  "msg": "操作成功",
  "data": [
    {
      "id": "7112",
      "no": "001",
      "name": "001",
      "area": "38",
      "status": "1",
      "status_name": "空闲",
      "area_name": "三层自习室",
      "point_x": "15.20833",
      "point_y": "13.95349",
      "width": "1.6666669999999999",
      "height": "3.003876"
    },
    {
      "id": "7113",
      "no": "002",
      "name": "002",
      "area": "38",
      "status": "2",
      "status_name": "已预约"
    }
  ]
}
```

**关键字段**

| 字段 | 说明 |
|------|------|
| `data[].id` | 座位唯一 ID，预约时使用 |
| `data[].no` | 座位编号 |
| `data[].name` | 座位名称（通常与编号一致） |
| `data[].status_name` | 座位状态：`空闲` / `已预约` / `使用中` 等 |

**选座逻辑**：过滤 `status_name == "空闲"` 的座位，收集 `{id, no}` 列表，然后随机选择一个。

**代码位置**：`py/get_info.py:221-275` (`get_seat_info`)

---

## 5. 阶段四：提交座位预约

### 5.1 确认预约座位

将选定的座位 ID 和时间段 segment 加密后提交预约。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://libyy.qfnu.edu.cn/api/Seat/confirm` |
| **Content-Type** | `application/json` |
| **鉴权** | `Authorization: bearer{token}` |

**请求体**

加密前的原始 JSON 字符串：

```json
{"seat_id":"7200","segment":"12346"}
```

将上述字符串经过 AES-CBC 加密（见附录 A）后，放入请求体：

```json
{
  "aesjson": "<AES加密后的Base64字符串>"
}
```

**请求头**

| Header | 值 |
|--------|-----|
| Content-Type | `application/json` |
| Connection | `keep-alive` |
| Accept | `application/json, text/plain, */*` |
| lang | `zh` |
| X-Requested-With | `XMLHttpRequest` |
| User-Agent | 标准浏览器 UA |
| Origin | `http://libyy.qfnu.edu.cn` |
| Referer | `http://libyy.qfnu.edu.cn/h5/index.html` |
| Authorization | `bearer{token}` |

**响应示例**

成功：
```json
{
  "code": 1,
  "msg": "预约成功"
}
```

失败：
```json
{
  "code": 0,
  "msg": "当前用户在该时段已存在座位预约，不可重复预约"
}
```

**所有可能的 `msg` 值见附录 D。**

**代码位置**：`py/get_seat_tomorrow_mode_1.py:436-474` (`post_to_get_seat`)

---

## 6. 阶段五：预约后操作

### 6.1 查询个人座位状态

查询当前用户的座位预约和使用情况。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://libyy.qfnu.edu.cn/api/Member/seat` |
| **Content-Type** | `application/json` |
| **鉴权** | `Authorization: bearer{token}` |

**请求体**

```json
{
  "page": 1,
  "limit": 3,
  "authorization": "bearer{token}"
}
```

**响应示例**

```json
{
  "code": 1,
  "msg": "操作成功",
  "data": {
    "data": [
      {
        "id": 99999,
        "name": "036",
        "nameMerge": "西校区图书馆-三层自习室 036",
        "statusName": "预约成功",
        "startTime": "08:00",
        "endTime": "22:00"
      }
    ]
  }
}
```

**关键字段**

| 字段 | 说明 |
|------|------|
| `data.data[].id` | 预约记录 ID（签退/取消时使用） |
| `data.data[].name` | 座位编号 |
| `data.data[].nameMerge` | 教室名 + 座位编号 |
| `data.data[].statusName` | 状态：`预约成功` / `使用中` / `已签退` 等 |

**代码位置**：`py/get_info.py:192-218` (`get_member_seat`)

---

### 6.2 签到（扫码入座）

模拟扫码签到。签到数据同样需要 AES 加密。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://libyy.qfnu.edu.cn/api/Seat/touch_qr_books` |
| **Content-Type** | `application/json` |
| **鉴权** | `authorization: bearer{token}` |

**请求体**

加密前的原始 JSON：
```json
{"method":"checkin"}
```

加密后的请求体：
```json
{
  "aesjson": "<AES加密后的Base64字符串>",
  "authorization": "bearer{token}"
}
```

**响应示例**

```json
{
  "code": 1,
  "msg": "签到成功"
}
```

**可能的 `msg` 值**

| msg | 说明 |
|-----|------|
| `签到成功` | 签到成功 |
| `使用中,不用重复签到！` | 已签到，无需重复 |
| `对不起，您的预约未生效` | 预约未生效 |

**代码位置**：`py/check_in.py:234-287` (`aes_encrypt`, `lib_rsv`)

---

### 6.3 签退（离座）

对正在使用中的座位进行签退操作。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://libyy.qfnu.edu.cn/api/Space/checkout` |
| **Content-Type** | `application/json` |
| **鉴权** | `Authorization: bearer{token}` |

**请求体**

```json
{
  "id": 99999,
  "authorization": "bearer{token}"
}
```

> `id` 为步骤 6.1 查询到的 `statusName == "使用中"` 的记录 ID。

**响应示例**

```json
{
  "code": 1,
  "msg": "完全离开操作成功"
}
```

**代码位置**：`py/sign_out.py:240-295` (`go_home`)

---

### 6.4 取消预约

取消尚未签到的座位预约（代码中定义了 URL 常量但未有独立调用逻辑，此处列出以备参考）。

| 项目 | 值 |
|------|-----|
| **方法** | `POST` |
| **URL** | `http://libyy.qfnu.edu.cn/api/Space/cancel` |
| **Content-Type** | `application/json` |
| **鉴权** | `Authorization: bearer{token}` |

**请求体**（推测）

```json
{
  "id": 99999,
  "authorization": "bearer{token}"
}
```

**响应**

```json
{
  "code": 1,
  "msg": "取消成功"
}
```

**代码位置**：URL 定义于 `py/get_seat_tomorrow_mode_1.py:38`

---

## 7. 附录

### A. AES 加密算法说明

预约请求和签到请求的数据均需经过 AES-CBC 加密。

**参数**

| 项目 | 值 |
|------|-----|
| 算法 | AES-128-CBC |
| 填充 | PKCS7 |
| 密钥（Key） | 当前日期 `YYYYMMDD` + 其回文，共 16 字节 |
| 初始向量（IV） | `ZZWBKJ_ZHIHUAWEI`（固定，16 字节） |
| 输出 | Base64 编码 |

**密钥生成示例**

```
日期：20260418
回文：81406202
密钥：2026041881406202（16字节）
```

**加密流程**

```
原始 JSON 字符串
    -> UTF-8 编码
    -> PKCS7 填充到 16 字节对齐
    -> AES-CBC 加密（Key + IV）
    -> Base64 编码
    -> 作为 aesjson 字段的值
```

**代码位置**：`py/get_info.py:136-165` (`get_key`, `encrypt`)

---

### B. IDS 密码加密算法说明

IDS 登录时密码需要经过 AES 加密。

**参数**

| 项目 | 值 |
|------|-----|
| 算法 | AES-128-CBC |
| 填充 | PKCS7 |
| 密钥（Key） | 步骤 2.1 获取的 `pwdEncryptSalt` 值 |
| 初始向量（IV） | 随机生成的 16 位字符串 |
| 明文 | 64 位随机字符串 + 原始密码 |
| 输出 | Base64 编码 |

**加密流程**

```
生成 64 位随机字符串 randomPrefix
生成 16 位随机字符串 iv
明文 = randomPrefix + 原始密码
    -> UTF-8 编码
    -> PKCS7 填充
    -> AES-CBC 加密（Key=salt, IV=iv）
    -> Base64 编码
```

> 随机字符串字符集：`ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678`

**代码位置**：`py/ids_utils/passwd_encrypt.py:8-65`

---

### C. 教室 ID 映射表

| 教室名称 | build_id |
|----------|----------|
| 西校区图书馆-二层自习室 | 45（仅 v3.1） |
| 西校区图书馆-三层自习室 | 38 |
| 西校区图书馆-四层自习室 | 39 |
| 西校区图书馆-五层自习室 | 40 |
| 西校区东辅楼-二层自习室 | 41 |
| 西校区东辅楼-三层自习室 | 42 |
| 东校区图书馆-三层电子阅览室 | 21 |
| 东校区图书馆-三层自习室01 | 22 |
| 东校区图书馆-三层自习室02 | 23 |
| 东校区图书馆-四层中文现刊室 | 24 |
| 综合楼-801自习室 | 16 |
| 综合楼-803自习室 | 17 |
| 综合楼-804自习室 | 18 |
| 综合楼-805自习室 | 19 |
| 综合楼-806自习室 | 20 |
| 行政楼-四层东区自习室 | 13 |
| 行政楼-四层中区自习室 | 14 |
| 行政楼-四层西区自习室 | 15 |
| 电视台楼-二层自习室 | 12 |

**代码位置**：`py/get_info.py:16-35`

---

### D. 预约状态码汇总

以下是 `/api/Seat/confirm` 接口返回的 `msg` 字段可能的值及处理策略：

| msg | 含义 | 处理策略 |
|-----|------|----------|
| `预约成功` | 座位预约成功 | 停止重试，查询预约详情 |
| `当前用户在该时段已存在座位预约，不可重复预约` | 已有预约 | 停止重试，查询已有预约 |
| `开放预约时间19:20` | 未到预约开放时间 | 等待 1 秒后重试 |
| `您尚未登录` | Token 失效 | 重新获取 Token 后重试 |
| `该空间当前状态不可预约` | 座位已被占用或不可用 | 换一个座位重试 |
| `取消成功` | 取消预约成功 | 退出程序 |

---

### E. 通用请求头模板

图书馆系统接口（阶段三至五）使用的通用请求头：

```
Content-Type: application/json
Connection: keep-alive
Accept: application/json, text/plain, */*
lang: zh
X-Requested-With: XMLHttpRequest
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0
Origin: http://libyy.qfnu.edu.cn
Referer: http://libyy.qfnu.edu.cn/h5/index.html
Accept-Encoding: gzip, deflate
Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6,pl;q=0.5
Authorization: bearer{token}
```

> 注意：获取教室时间段（4.1）和座位列表（4.2）接口不需要 `Authorization` 头；仅涉及用户操作的接口（预约、查询个人座位、签到、签退）需要。
