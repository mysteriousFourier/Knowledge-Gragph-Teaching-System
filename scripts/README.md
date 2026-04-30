# 脚本

`scripts/` 保存本地启动、停止和维护辅助脚本。

## 常用脚本

| 脚本 | 用途 |
| --- | --- |
| `resolve_python.ps1` | 按 `.env` 和本机环境查找 Python |

根目录的 `start.bat` 是推荐启动入口，它会调用后端编排器并自动打开主页。

## 使用方式

启动：

```bat
start.bat
```

停止：

```powershell
powershell -ExecutionPolicy Bypass -File stop.ps1
```

更多细节见 [脚本模块文档](../docs/modules/scripts.md)。
