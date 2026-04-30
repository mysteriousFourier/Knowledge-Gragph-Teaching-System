# Frontend Module

`frontend/` 是 Knowledge-Gragph-Teaching-System 的静态前端模块，包含首页、教师端、学生端、图谱查看页和共享视觉资源。

## 入口页面

| 页面 | 文件 | 说明 |
| --- | --- | --- |
| 首页 | `index.html` | 项目主入口 |
| 教师端 | `teacher.html` | 授课文案、章节导入、图谱维护 |
| 学生端 | `student.html` | 章节学习、练习题、问答 |
| 图谱查看页 | `graph-viewer.html` | Cytoscape.js 图谱查看 |

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
