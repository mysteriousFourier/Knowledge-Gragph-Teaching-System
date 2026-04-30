# 前端模块

前端模块位于 `frontend/`，由静态 HTML、CSS 和 JavaScript 组成。项目不依赖前端构建工具，所有页面由 `backend/frontend_server.py` 或任意静态服务器直接提供。

## 页面入口

| 页面 | 路径 | 主要职责 |
| --- | --- | --- |
| 首页 | `frontend/index.html` | 展示项目入口，跳转教师端、学生端、图谱管理 |
| 教师端 | `frontend/teacher.html` | 登录、章节导入、授课文案生成、图谱维护、自然补充 |
| 学生端 | `frontend/student.html` | 登录、章节学习、练习题、问答、学习路径 |
| 图谱查看页 | `frontend/graph-viewer.html` | 使用 Cytoscape.js 查看知识图谱 |
| 旧图谱页 | `frontend/graph.html` | 兼容旧入口或实验页面 |
| API 配置页 | `frontend/api-config.html` | 本地调试辅助页面 |

## 样式和脚本

| 文件 | 说明 |
| --- | --- |
| `home.css`, `home.js` | 首页视觉和交互 |
| `workspace-ambient.css`, `workspace-ambient.js` | 黑色字符波纹背景、呼吸动效、液态玻璃基础视觉 |
| `styles.css`, `new-styles.css` | 教师端和通用页面样式 |
| `student-styles.css` | 学生端布局和题目交互样式 |
| `teacher.js` | 教师端业务交互、API 调用、图谱视图 |
| `student.js` | 学生端登录、章节、练习题、问答和学习路径 |
| `graph-viewer.css` | 图谱查看页样式 |
| `graph-styles.css` | 旧图谱视图样式 |

## API 配置

前端通过 `frontend/env-config.js` 读取后端服务地址。该文件由启动器生成，不提交到 Git。

默认地址：

| 配置字段 | 默认值 |
| --- | --- |
| `educationApiBaseUrl` | `http://localhost:8001` |
| `maintenanceApiBaseUrl` | `http://localhost:8002` |
| `backendAdminBaseUrl` | `http://localhost:8080` |

页面脚本会使用本地默认值兜底，但部署和本地启动时应优先依赖 `window.__APP_CONFIG__`。

## 教师端数据流

```text
教师登录
  -> 选择或导入章节
  -> 调用教育 API 生成授课文案
  -> 调用维护 API 查询或更新图谱
  -> 保存章节和授课文案到运行期章节缓存
  -> 前端刷新文案、图谱和一致性报告
```

主要 API：

- `POST /api/teacher/login`
- `POST /api/education/generate-lecture`
- `POST /api/education/natural-supplement`
- `POST /api/education/save-chapter`
- `POST /api/education/save-lecture`
- `GET /api/education/graph`
- `POST /api/maintenance/search-nodes`
- `POST /api/maintenance/scan-structured`

## 学生端数据流

```text
学生登录
  -> 获取章节
  -> 加载预创建题库或触发题库生成
  -> 点击选项完成选择
  -> 提交答案并接收反馈
  -> 通过问答接口获取图谱约束回答
```

主要 API：

- `POST /api/student/login`
- `GET /api/student/chapter`
- `POST /api/student/generate-exercises`
- `GET /api/student/exercises`
- `POST /api/student/check-answer`
- `POST /api/student/question`
- `POST /api/student/learning-path`
- `GET /api/student/prerequisites`
- `GET /api/student/follow-up`

## 视觉规范

- 前端背景使用字符明暗变化表现波纹、扩散和呼吸效果。
- 教师端和学生端内容区使用液态玻璃边框，避免纯黑纯白大块遮挡背景。
- 内容可读性优先于动效表现，表单、题目、文案和图谱区域必须保持足够对比度。
- 新增面板时应复用现有玻璃层、按钮、状态标签和输入框样式，避免引入新的视觉体系。

## 新增页面规则

1. 页面必须从 `env-config.js` 读取服务地址。
2. 登录或敏感操作不得在前端硬编码真实凭据。
3. 业务错误需要显示明确状态，不只写入控制台。
4. 新增 API 调用时同步更新对应后端模块文档。
5. 新增 CSS 时应检查移动端宽度，避免文字和按钮溢出。
