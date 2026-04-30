# 辅助脚本模块

辅助脚本模块覆盖根目录启动停止脚本和 `scripts/` 目录。脚本目标是让 Windows 本地开发环境可重复启动和停止，不要求读者手动拼接多个命令。

## 脚本清单

| 路径 | 职责 |
| --- | --- |
| `start.bat` | 加载 `.env`、解析 Python、启动 `backend/start_all.py` |
| `stop.ps1` | 根据 pid 文件和默认端口停止本地服务 |
| `scripts/resolve_python.ps1` | 辅助解析可用 Python 解释器 |

## start.bat

启动脚本执行顺序：

1. 切换代码页为 UTF-8。
2. 进入项目根目录。
3. 读取 `.env`。
4. 按优先级解析 Python：
   - `PYTHON_EXE`
   - `CONDA_ENV_PYTHON`
   - `CONDA_ROOT + CONDA_ENV_NAME`
   - `.venv\Scripts\python.exe`
   - `venv\Scripts\python.exe`
   - `where python`
   - `scripts\resolve_python.ps1`
5. 如果配置了 Conda 环境，尝试激活。
6. 执行 `backend/start_all.py`。

## stop.ps1

停止脚本执行顺序：

1. 加载 `.env`。
2. 读取 `.runtime/knowledge-gragph-teaching-system-processes.json`。
3. 按 PID 停止已记录服务。
4. 扫描默认端口并停止残留监听进程。
5. 删除 pid 文件。
6. 输出剩余端口占用情况。

自动化使用时可加 `-NoPause`，避免脚本等待回车：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1 -NoPause
```

## 脚本编写规范

- 新脚本应放入 `scripts/`，根目录只保留用户高频直接执行的入口脚本。
- PowerShell 脚本应使用 `-LiteralPath` 处理路径，避免路径中空格或特殊字符导致误操作。
- 涉及删除、移动或停止进程的脚本必须先解析目标路径或 PID，并给出清晰输出。
- 脚本不应写死个人电脑路径、真实 API key 或账号密码。
- 新增脚本后需要更新本文档、根 README 的目录结构和 Git 添加建议。

## 常见维护任务

检查 Python 解释器：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\resolve_python.ps1
```

启动项目：

```bat
start.bat
```

停止项目：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\stop.ps1
```
