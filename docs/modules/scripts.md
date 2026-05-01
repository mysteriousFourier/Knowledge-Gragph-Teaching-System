# 脚本模块

脚本用于降低本地运行和排错成本。脚本应保持可读、可重复执行，并避免误杀无关进程。

## 启动

本地多端口开发推荐：

```bat
start.bat
```

它会调用后端编排器，启动完整系统并打开主页。

单端口 FastAPI / Render 本地验证推荐：

```bat
start_render_local.bat
```

指定端口：

```bat
start_render_local.bat 3100
```

该脚本会设置本地运行时目录，调用 `uvicorn render_app:app`，并自动打开 `http://127.0.0.1:<端口>/`。它不会启动 `8001`、`8002`、`8080` 等额外公开端口。

## 停止

推荐停止方式：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_unlesspaper.ps1
```

停止脚本应：

- 优先读取 `.runtime/processes.json`。
- 检查默认端口。
- 只停止属于本项目的进程。
- 输出清晰结果，避免窗口闪退后无法判断状态。

## Python 解析

`resolve_python.ps1` 根据 `.env` 和本机环境寻找 Python。优先级通常是：

1. `PYTHON_EXE`
2. `CONDA_ENV_PYTHON`
3. Conda 环境配置
4. 系统 PATH

## 维护规则

- 不在脚本中写死个人路径。
- 不在脚本中写 API Key。
- 删除或移动文件前要限制目标路径。
- 新增脚本后更新本文件和根 README。
- 启动脚本打印的地址应使用 `127.0.0.1`，避免与历史 `localhost` 默认值混用。
