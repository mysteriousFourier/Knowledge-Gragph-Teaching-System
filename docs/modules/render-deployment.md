# Render 单服务部署

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

前端仍加载 `env-config.js`，但在 Render 单服务中该文件由 `render_app.py` 动态返回，默认把所有 API 基础地址指向 `window.location.origin`，因此不再请求 `localhost:8001` 或 `localhost:8002`。

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
APP_RUNTIME_DIR=/opt/render/project/src/.runtime
APP_DATA_DIR=/opt/render/project/src/.render-data
GRAPH_DB_PATH=
```

## 持久化

Render 普通 Web Service 文件系统适合临时运行，不适合长期保存题库反馈和图谱数据库。若需要长期保存：

1. 在 Render 服务上添加 Persistent Disk。
2. 假设挂载路径是 `/var/data`。
3. 设置环境变量：

```text
APP_RUNTIME_DIR=/var/data/runtime
GRAPH_DB_PATH=/var/data/knowledge_graph.db
```

这样 `.runtime/chapters.json`、题库反馈和图谱数据库就不会随重新部署丢失。

## 本地验证

在本地可直接运行：

```powershell
uvicorn render_app:app --host 127.0.0.1 --port 3000
```

然后打开：

```text
http://127.0.0.1:3000/
http://127.0.0.1:3000/teacher.html
http://127.0.0.1:3000/student.html
http://127.0.0.1:3000/admin
```

原本的 `start.bat` 仍保留给本地多服务开发使用。
