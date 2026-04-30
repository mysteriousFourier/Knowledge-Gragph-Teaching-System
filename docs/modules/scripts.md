# 脚本模块

脚本用于降低本地运行和排错成本。脚本应保持可读、可重复执行，并避免误杀无关进程。

## 启动

推荐启动方式：

```bat
start.bat
```

它会调用后端编排器，启动完整系统并打开主页。

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
