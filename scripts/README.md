# 脚本

`scripts/` 保存本地启动、停止和维护辅助脚本。

## 常用脚本

| 脚本 | 用途 |
| --- | --- |
| `stop_unlesspaper.ps1` | 根据运行时记录和端口安全停止本项目服务 |
| `resolve_python.ps1` | 按 `.env` 和本机环境查找 Python |

根目录的 `start.bat` 是多端口本地开发启动入口，它会调用后端编排器并自动打开主页。

根目录的 `start_render_local.bat` 是单端口 FastAPI 本地验证入口，用于模拟 Render 部署形态，默认打开 `http://127.0.0.1:3000/`。

## 使用方式

启动：

```bat
start.bat
```

单端口验证：

```bat
start_render_local.bat
```

停止：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_unlesspaper.ps1
```

更多细节见 [脚本模块文档](../docs/modules/scripts.md)。
