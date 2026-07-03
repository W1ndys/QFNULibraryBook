# QFNULibraryBook 项目文件夹整理规格

**修订**: v3（第二轮审核后修订）

## 1. 目的

消除 `py/` 目录的混杂状态，将工具脚本、用户配置文件、调试产物分离到独立目录，使项目结构清晰、职责分明。

## 2. 边界

| 范围 | 说明 |
|------|------|
| **包含** | `py/` 根目录下的配置文件、调试产物、工具脚本、`__pycache__/` 缓存 |
| **包含** | `py/config/config.py` `from_yaml()` 路径解析逻辑微调 |
| **包含** | `scripts/` 下所有脚本的导入路径动态适配（`sys.path.insert`） |
| **包含** | 入口脚本的 docstring 和 argparse help 文本更新 |
| **不包含** | `py/api/`、`py/auth/`、`py/crypto/`、`py/notify/` 等模块子目录 |
| **不包含** | `.github/`、`assets/`、`json/`、`tests/`、`claude-context/` |
| **不包含** | `py/get_seat.py`、`py/check_in.py`、`py/sign_out.py` 等主入口文件（仅更新其 docstring 和 help 文本） |
| **不包含** | 大规模代码逻辑重构或功能修改 |

## 3. 技术方案

### 3.1 清理缓存和调试产物

**操作：**
- 物理删除 `py/debug_captcha/` 下 28 个 PNG 文件（~8.1MB）
- 使用 `git rm --cached -r` 将已跟踪的 `__pycache__/` 目录从 Git 中移除（保留磁盘文件但不再跟踪，后续物理删除）
- 物理清理所有 `__pycache__/` 目录（清除 .pyc 缓存）
- 确认 `.gitignore` 已覆盖：`__pycache__/`、`*.pyc`、`*.pyo`、`.pytest_cache/`、`debug_captcha/`

**风险与回退：**
- `git rm --cached` 仅从 Git 移除，不删除磁盘文件，可安全回退
- 调试图片可通过 `git checkout -- py/debug_captcha/` 恢复

### 3.2 目录重组

#### 新建 `scripts/` 目录

存放与核心业务无关的工具/探测脚本：

| 原路径 | 新路径 | 文件类型 |
|--------|--------|----------|
| `py/run_all.py` | `scripts/run_all.py` | 多用户运行脚本 |
| `py/performance_probe.py` | `scripts/performance_probe.py` | API 性能探测 |
| `py/time_window_test.py` | `scripts/time_window_test.py` | 预约窗口测试 |
| `py/performance_results.json` | `scripts/performance_results.json` | 性能测试数据 |

**`scripts/*.py` 导入修复**：
这三个脚本移动到 `scripts/` 后，其原始 `sys.path` 操作将不再有效。需要统一修复：

| 脚本 | 当前路径操作 | 修改后 |
|------|-------------|--------|
| `run_all.py` | 无 `sys.path` 操作（依赖 CWD=py/） | 在 import 之前插入 `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'py'))` |
| `performance_probe.py` | `sys.path.insert(0, ".")`（第18行） | 替换为 `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'py'))` |
| `time_window_test.py` | `sys.path.insert(0, ".")`（第16行） | 替换为 `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'py'))` |

确保从项目根目录直接运行 `python scripts/<script>.py` 可正确导入 `py/` 下的模块。

**`scripts/run_all.py` 内部路径更新**：

| 行号 | 旧值 | 新值 |
|------|------|------|
| 第5行（docstring） | `py/config/users.yml` | `configs/users.yml` |
| 第6行（docstring） | `py/config/users.yml` | `configs/users.yml` |
| 第7行（docstring） | `py/config/users.yml` | `configs/users.yml` |
| 第9行（docstring） | `py/config/users.yml` | `configs/users.yml` |
| 第58行（错误提示） | `config: config_studentA.yml` | `config: studentA.yml` |
| 第237行（default） | `py/config/users.yml` | `configs/users.yml` |
| 第238行（help） | `py/config/users.yml` | `configs/users.yml` |

#### 新建 `configs/` 目录

存放用户级 YAML 配置文件。注意与 `py/config/` 区分：`py/config/` 存放 Python 配置管理模块代码（`config.py`），`configs/` 仅存放用户级 YAML 配置文件。

| 原路径 | 新路径 | 文件类型 |
|--------|--------|----------|
| `py/config_studentA.yml` | `configs/studentA.yml` | 学生 A 配置 |
| `py/config_studentB.yml` | `configs/studentB.yml` | 学生 B 配置 |
| `py/config.yml` | `configs/template.yml` | 配置模板 |
| `py/config/users.yml` | `configs/users.yml` | 用户管理配置 |

**`configs/users.yml` 内部引用更新**：

| 行号 | 旧值 | 新值 |
|------|------|------|
| 第6行 | `config: config_studentA.yml` | `config: studentA.yml` |
| 第9行 | `config: config_studentB.yml` | `config: studentB.yml` |

### 3.3 代码适配

#### `py/config/config.py` — `from_yaml()` 路径解析修复

**当前问题**：第 44-53 行将相对路径基于 `py/` 目录解析，配置文件移到 `configs/` 后无法找到。

**修改方案**：

```python
# 修改前（第 44-53 行）
current_dir = os.path.dirname(os.path.abspath(__file__))  # py/config/
py_dir = os.path.dirname(current_dir)                      # py/

if config_file is None:
    config_path = os.path.join(py_dir, "config.yml")
elif os.path.isabs(config_file):
    config_path = config_file
else:
    config_path = os.path.join(py_dir, config_file)

# 修改后
current_dir = os.path.dirname(os.path.abspath(__file__))  # py/config/
py_dir = os.path.dirname(current_dir)                      # py/
project_root = os.path.dirname(py_dir)                      # 项目根目录

if config_file is None:
    config_path = os.path.join(project_root, "configs", "template.yml")
elif os.path.isabs(config_file):
    config_path = config_file
else:
    # 优先从项目根目录解析；如不存在则回退到 py/ 目录
    # 注意：git mv 已移动的文件不会出现在旧 py/ 位置，回退仅保障尚未移动的文件
    config_path = os.path.join(project_root, config_file)
    if not os.path.exists(config_path):
        config_path = os.path.join(py_dir, config_file)
```

**向后兼容性说明**：
- `git mv` 后的配置文件（`configs/studentA.yml` 等）通过新路径 `-c configs/studentA.yml` 访问
- 旧路径 `-c config_studentA.yml` 不再有效——文件已不在 `py/` 下，也不在项目根目录下
- `from_yaml()` 的回退逻辑保障尚未移出 `py/` 的文件仍可通过相对路径加载

#### 入口脚本 docstring 和 argparse help 文本更新

**docstring 更新**（所有脚本已移至新位置，docstring 反映最终位置）：

| 文件 | 行 | 旧值 | 新值 |
|------|-----|------|------|
| `py/get_seat.py` | 第3行 | `python get_seat.py [-c config_studentA.yml]` | `python get_seat.py [-c configs/studentA.yml]` |
| `py/check_in.py` | 第3行 | `python check_in.py [-c config_studentA.yml]` | `python check_in.py [-c configs/studentA.yml]` |
| `py/sign_out.py` | 第3行 | `python sign_out.py [-c config_studentA.yml]` | `python sign_out.py [-c configs/studentA.yml]` |
| `py/get_seat_info_ForAdmin.py` | 第3行 | `python get_seat_info_ForAdmin.py [-c config.yml]` | `python get_seat_info_ForAdmin.py [-c configs/template.yml]` |
| `scripts/performance_probe.py` | 第5行 | `python performance_probe.py -c config_studentA.yml` | `python scripts/performance_probe.py -c configs/studentA.yml` |
| `scripts/time_window_test.py` | 第5行 | `python time_window_test.py -c config_studentA.yml` | `python scripts/time_window_test.py -c configs/studentA.yml` |

**argparse `help` 文本更新**：

| 文件 | 行 | 旧值 | 新值 |
|------|-----|------|------|
| `py/get_seat.py` | 第252行 | `"指定配置文件路径，默认为 config.yml"` | `"指定配置文件路径，默认为 configs/template.yml"` |
| `py/check_in.py` | 第71行 | `"指定配置文件路径，默认为 config.yml"` | `"指定配置文件路径，默认为 configs/template.yml"` |
| `py/sign_out.py` | 第73行 | `"指定配置文件路径，默认为 config.yml"` | `"指定配置文件路径，默认为 configs/template.yml"` |
| `py/get_seat_info_ForAdmin.py` | 第103行 | `"指定配置文件路径，默认为 config.yml"` | `"指定配置文件路径，默认为 configs/template.yml"` |

### 3.4 CI 工作流更新

| 文件 | 行 | 旧值 | 新值 |
|------|-----|------|------|
| `.github/workflows/check_in.yml` | 第27行 | `python py/check_in.py -c config_studentA.yml` | `python py/check_in.py -c configs/studentA.yml` |
| `.github/workflows/check_in.yml` | 第28行 | `python py/check_in.py -c config_studentB.yml` | `python py/check_in.py -c configs/studentB.yml` |
| `.github/workflows/sign_out.yml` | 第27行 | `python py/sign_out.py -c config_studentA.yml` | `python py/sign_out.py -c configs/studentA.yml` |
| `.github/workflows/sign_out.yml` | 第28行 | `python py/sign_out.py -c config_studentB.yml` | `python py/sign_out.py -c configs/studentB.yml` |

**前置依赖**：CI 工作流路径更新依赖 3.3 节 `from_yaml()` 路径解析修复已完成。CI 的 CWD 为项目根目录，`python py/check_in.py` 运行时 `py/` 自动在 sys.path 中，不受影响。

### 3.5 测试影响评估

- `pytest.ini` 设置 `pythonpath = py`，所有测试通过 `conftest.py` 的 `tmp_path` fixture 加载绝对路径或项目根相对路径的配置，**不受 `from_yaml()` 路径解析修改的影响**
- `tests/test_config.py` 中 `test_none_uses_default_path` 的 docstring 提及"`py/` 目录下的 `config.yml`"，需更新为"项目根目录下的 `configs/template.yml`"

### 3.6 CLAUDE.md 更新

| 位置 | 旧值 | 新值 |
|------|------|------|
| Commands 块 `python py/get_seat.py -c config_studentA.yml` | 原值 | `-c configs/studentA.yml` |
| Commands 块 `python py/check_in.py -c config_studentA.yml` | 原值 | `-c configs/studentA.yml` |
| Commands 块 `python py/sign_out.py -c config_studentA.yml` | 原值 | `-c configs/studentA.yml` |
| 目录结构 `py/` 块 | 未展示 `scripts/` 和 `configs/` | 增加 `configs/` 和 `scripts/` 目录说明 |
| Key Technical Details "配置文件位于 `py/` 目录下" | 原值 | "用户配置文件位于 `configs/` 目录下；Python 配置模块在 `py/config/`" |
| 新建 — 多用户运行命令 | — | `python scripts/run_all.py seat -u configs/users.yml` |
| 目录职责区分 | 无 | 新增：`py/config/` 存放 Python 配置管理模块；`configs/` 存放用户级 YAML |

### 3.7 最终目录结构

```
QFNULibraryBook/
├── .github/workflows/          # CI/CD（已更新路径）
├── assets/                     # 图片资产
├── claude-context/             # 项目文档（规格、设计等）
│   ├── designs/
│   ├── docs/
│   └── specs/
├── configs/                    # [新] 用户级 YAML 配置文件
│   ├── studentA.yml            # ← 原 py/config_studentA.yml
│   ├── studentB.yml            # ← 原 py/config_studentB.yml
│   ├── template.yml            # ← 原 py/config.yml
│   └── users.yml               # ← 原 py/config/users.yml
├── json/seat_info/             # 静态座位布局数据
├── py/                        # Python 源码
│   ├── api/                    # API 层（constants, http, exceptions）
│   ├── auth/                   # 认证（login, token）
│   ├── config/                 # 配置管理模块代码（config.py）
│   ├── crypto/                 # 加密（aes）
│   ├── notify/                 # 消息推送（notify）
│   ├── classrooms.py           # 教室映射
│   ├── get_info.py             # 座位信息查询
│   ├── get_seat.py             # 预约入口
│   ├── check_in.py             # 签到入口
│   ├── sign_out.py             # 签退入口
│   └── get_seat_info_ForAdmin.py  # 管理员工具
├── scripts/                    # [新] 工具/探测脚本
│   ├── run_all.py              # ← 原 py/run_all.py
│   ├── performance_probe.py    # ← 原 py/performance_probe.py
│   ├── time_window_test.py    # ← 原 py/time_window_test.py
│   └── performance_results.json # ← 原 py/performance_results.json
├── tests/                      # 测试
├── .gitignore
├── CLAUDE.md
├── README.md
├── requirements.txt
├── requirements-dev.txt
└── pytest.ini
```

## 4. 成功标准

- [ ] `git status` 显示干净的预期变更
- [ ] `__pycache__/` 和 `debug_captcha/` 不再被 Git 跟踪
- [ ] `scripts/` 目录含 4 个文件，`python scripts/run_all.py seat -u configs/users.yml` 可正常导入和运行
- [ ] `scripts/performance_probe.py` 和 `scripts/time_window_test.py` 的 `sys.path` 已修复，可从项目根目录运行
- [ ] `configs/` 目录含 4 个配置文件，`users.yml` 内部引用已更新
- [ ] `python py/get_seat.py -c configs/studentA.yml` 可正确加载配置
- [ ] 所有入口脚本的 docstring、argparse help 文本、CLAUDE.md、CI 工作流中的路径指向新位置
- [ ] `pytest` 测试全部通过

**明确不兼容的旧用法**（`git mv` 后旧路径不再可用）：
- `python py/get_seat.py -c config_studentA.yml` — 文件已移至 `configs/studentA.yml`
- `python py/run_all.py` — 脚本已移至 `scripts/run_all.py`

## 5. 实施步骤

### 步骤 1：清理缓存和调试产物
1. `git rm -r --cached` 移除所有 `__pycache__/` 目录
2. 物理删除所有 `__pycache__/` 目录
3. 物理删除 `py/debug_captcha/` 目录
4. 删除 `.pytest_cache/`
5. 确认 `.gitignore` 覆盖模式
6. 提交：`chore: 清理 __pycache__ 和 debug_captcha 调试产物`

### 步骤 2：修改 `py/config/config.py` 路径解析（前置依赖）
1. 修改 `from_yaml()` 方法：引入 `project_root`，优先项目根目录解析，回退 py/ 目录
2. 默认路径从 `config.yml` → `configs/template.yml`
3. **验证**：`python py/get_seat.py -h` 可正常导入

### 步骤 3：创建目录并移动文件
1. 创建 `scripts/` 和 `configs/` 目录
2. `git mv` 移动所有 8 个文件到新位置
3. 修复 `scripts/run_all.py`：`sys.path.insert()`、docstring、default、help
4. 修复 `scripts/performance_probe.py`：`sys.path.insert()`、docstring
5. 修复 `scripts/time_window_test.py`：`sys.path.insert()`、docstring
6. 更新 `configs/users.yml` 内部引用
7. **验证**：`python scripts/run_all.py seat --help` 可正常运行
8. 提交：`refactor: 分离工具脚本到 scripts/，用户配置到 configs/`

### 步骤 4：更新文档和引用
1. 更新入口脚本 docstring 和 argparse help 文本
2. 更新 CI 工作流
3. 更新 `CLAUDE.md`
4. 更新 `tests/test_config.py` 中过时的 docstring
5. **验证**：`pytest` 全部通过
6. 提交：`docs: 更新所有路径引用指向新目录结构`

## 6. 应急预案

| 异常 | 处理 |
|------|------|
| 移动文件后发现 import 错误 | `git checkout -- <文件>` 还原，调整后再试 |
| `from_yaml()` 路径修改后现有调用失败 | 回退兼容逻辑已内置（fallback 到 py/ 目录） |
| 某个脚本 `sys.path` 修复后仍导入失败 | 检查 `__file__` 解析，逐个验证 `python scripts/<name>.py --help` |
| `git rm --cached` 误操作 | `git reset HEAD <文件>` 恢复跟踪 |
| 提交后发现问题 | `git revert <commit-hash>` 回退 |
| CI 运行失败 | `from_yaml()` 依赖项目根目录 CWD（CI 已满足）；检查 CI 日志确认路径 |