# Frontend Module

`frontend/` 是 Knowledge-Gragph-Teaching-System 的静态前端模块，包含首页、教师端、学生端、图谱查看页和共享视觉资源。

## 入口页面

| 页面 | 文件 | 说明 |
| --- | --- | --- |
| 首页 | `index.html` | 项目主入口 |
| 教师端 | `teacher.html` | 授课文案、章节导入、图谱维护 |
| 学生端 | `student.html` | 章节学习、练习题、问答 |
| 图谱查看页 | `graph-viewer.html` | Cytoscape.js 图谱查看 |

## 共享渲染

| 文件 | 说明 |
| --- | --- |
| `latex-renderer.js` | 基于 KaTeX auto-render 的全局 LaTeX 渲染器 |
| `latex-renderer.css` | 公式在液态玻璃界面和普通页面中的样式 |
| `markdown-renderer.js` | 本地 Markdown 渲染器，用于课程内容、授课文案、问答和练习题 |
| `markdown-renderer.css` | 与液态玻璃界面统一的 Markdown 排版样式 |

支持 `$$...$$`、`\[...\]`、`\(...\)` 和 `$...$`。学生端和教师端动态生成的课程内容、回答和练习题会自动补渲染公式。

## 运行方式

推荐使用根目录启动脚本：

```bat
start.bat
```

默认访问：

```text
http://localhost:3000/
```

## 配置

前端通过运行期文件 `env-config.js` 读取后端地址。该文件由 `backend/start_all.py` 生成，默认不提交到 Git。

## 详细文档

完整说明见 [docs/modules/frontend.md](../docs/modules/frontend.md)。
