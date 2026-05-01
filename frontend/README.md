# 前端

`frontend/` 是纯静态前端目录，不需要构建工具即可运行。页面通过 `backend/frontend_server.py` 或任意静态服务器提供，默认访问地址为 `http://127.0.0.1:3000/`。

## 页面

| 文件 | 用途 |
| --- | --- |
| `index.html` | 主页，加载本地 `home.css` 和 `home.js` |
| `teacher.html` | 教师端 |
| `student.html` | 学生端 |
| `graph.html` | 图谱后台跳转页 |
| `graph-viewer.html` | 前端图谱查看页 |

## 核心脚本

| 文件 | 职责 |
| --- | --- |
| `home.js` | 主页字符背景、鼠标波纹、点击扩散和滚动上浮动效 |
| `teacher.js` | 教师端交互、授课文案、题库、反馈、问答 |
| `student.js` | 学生端课程、练习题、问答、图谱交互 |
| `markdown-renderer.js` | Markdown 渲染 |
| `latex-renderer.js` | LaTeX 渲染 |
| `workspace-ambient.js` | 字符波纹背景 |

## 渲染链路

用户可见的富文本应先经过 Markdown 渲染，再经过 LaTeX 渲染。课程内容、授课文案、问答、题目、选项和图谱详情都应使用统一链路，避免同类内容在不同页面表现不一致。

## 配置

`frontend/env-config.js` 由启动脚本生成，不提交到 Git。它负责告诉静态页面后端 API 地址和当前端口。

单端口 FastAPI 模式不会读取本地 `frontend/env-config.js`，而是由 `/env-config.js` 动态返回同源 API 地址。

主页不加载远程 CDN，避免外部网络阻塞入口动效。教师端、学生端和图谱页面需要公式或图谱库时，可继续按页面需要加载外部资源或本地 fallback。

更多细节见 [前端模块文档](../docs/modules/frontend.md)。
