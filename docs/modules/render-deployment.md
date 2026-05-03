# Render 单服务部署

## 重要提示：render可能也需要信用卡注册，相比之下有更好的选择Oracle cloud。如只有借记卡且不考虑注册，可以使用Microsoft的Azure

本页是 Render 平台部署说明。若需要先理解当前单端口版本的运行边界、路径和本地验证流程，请先阅读 [单端口 FastAPI 版本](single-port-fastapi.md)。

本分支提供 Render 适配入口：`render_app.py`。它把静态前端、教育 API、维护 API 和图谱后台挂到同一个 FastAPI Web Service 中，适配 Render 的单公开端口模型。

## 线上路径

部署成功后，常用入口如下：

```text
/                         主页
/teacher.html             教师端
/student.html             学生端
/admin                    图谱后台
/api/health               健康检查
/api/education/...        教师端教育接口
/api/student/...          学生端接口
/api/maintenance/...      图谱维护接口
```

前端仍加载 `env-config.js`，但在 Render 单服务中该文件由 `render_app.py` 动态返回，默认把所有 API 基础地址指向 `window.location.origin`，因此不再请求 `127.0.0.1:8001` 或 `127.0.0.1:8002`。

## Render 配置

仓库根目录提供 `render.yaml`。在 Render 中创建 Blueprint 或 Web Service 时可使用：

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn render_app:app --host 0.0.0.0 --port $PORT
Health Check Path: /api/health
```

必须在 Render 环境变量中配置：

```text
DEEPSEEK_API_KEY
APP_STUDENT_PASSWORD
APP_TEACHER_PASSWORD
```

可选配置：

```text
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
DEEPSEEK_GENERATION_READ_TIMEOUT_SECONDS=0
APP_RUNTIME_DIR=/opt/render/project/src/.runtime
APP_DATA_DIR=/opt/render/project/src/.render-data
GRAPH_DB_PATH=
RENDER_AUTO_SYNC_STRUCTURED=1
RENDER_AUTO_SYNC_MIN_NODES=20
```

单服务启动时会在图谱节点过少时自动从 `structured/` 同步图谱。可用下面的环境变量关闭：

```text
RENDER_AUTO_SYNC_STRUCTURED=0
```

## 持久化

Render 普通 Web Service 文件系统适合临时运行，不适合长期保存题库反馈和图谱数据库。若需要长期保存：

1. 在 Render 服务上添加 Persistent Disk。
2. 假设挂载路径是 `/var/data`。
3. 设置环境变量：

```text
APP_RUNTIME_DIR=/var/data/runtime
APP_DATA_DIR=/var/data/app-data
GRAPH_DB_PATH=/var/data/knowledge_graph.db
```

这样 `.runtime/chapters.json`、题库反馈和图谱数据库就不会随重新部署丢失。

## 本地验证

在本地可直接运行：

```powershell
uvicorn render_app:app --host 127.0.0.1 --port 3000
```

也可以直接双击根目录的：

```text
start_render_local.bat
```

如需换端口：

```bat
start_render_local.bat 3100
```

然后打开：

```text
http://127.0.0.1:3000/
http://127.0.0.1:3000/teacher.html
http://127.0.0.1:3000/student.html
http://127.0.0.1:3000/admin
```

原本的 `start.bat` 仍保留给本地多服务开发使用。

## 部署后检查

部署完成后按顺序检查：

1. 打开 `/api/health`，确认返回健康状态。
2. 打开 `/`，确认主页字符背景和滚动上浮动效存在。
3. 打开 `/teacher.html`，确认可登录、生成授课文案、继续生成题库。
4. 打开 `/student.html`，确认可加载课程内容、练习题和侧边问答。
5. 打开 `/admin`，确认图谱后台可见，并且节点详情中的 Markdown/LaTeX 可渲染。

如果图谱后台只有极少节点，先确认 `structured/` 是否随仓库部署，再检查 `RENDER_AUTO_SYNC_STRUCTURED` 和 `RENDER_AUTO_SYNC_MIN_NODES`。
