# 文档索引

这里保存 Knowledge-Gragph-Teaching-System 的维护者文档。根目录 [README.md](../README.md) 面向首次使用者，本文档目录面向后续维护、二次开发和代码审查。

## 模块文档

| 文档 | 内容 |
| --- | --- |
| [单端口 FastAPI 版本](modules/single-port-fastapi.md) | 当前 Render 兼容版本的入口、路径、运行方式、持久化和验证清单 |
| [运行时与配置](modules/runtime-and-configuration.md) | `.env`、端口、启动、停止、运行时生成文件 |
| [后端编排器](modules/backend-orchestrator.md) | `backend/start_all.py`、服务生命周期、进程记录 |
| [前端](modules/frontend.md) | 静态页面、Markdown/LaTeX、教师端和学生端交互 |
| [教育 API](modules/education-api.md) | 授课文案、问答、练习题、题目反馈、图谱证据 |
| [维护 API](modules/maintenance-api.md) | 图谱导入、节点/关系编辑、结构化同步、导出 |
| [知识图谱与向量后端](modules/knowledge-graph-vector.md) | SQLite 图谱服务、搜索、前端图谱数据归一化 |
| [MCP 服务](modules/mcp-server.md) | MCP 兼容图谱工具桥接 |
| [数据资产](modules/data-assets.md) | 结构化章节、公式库、运行时缓存、忽略规则 |
| [脚本](modules/scripts.md) | 启动、停止和辅助脚本 |
| [Render 单服务部署](modules/render-deployment.md) | Render Web Service 部署入口、环境变量、持久化 |

## 目录 README

- [后端总览](../backend/README.md)
- [教育 API](../backend/education/README.md)
- [维护 API](../backend/maintenance/README.md)
- [MCP 服务](../backend/mcp-server/README.md)
- [图谱后端](../backend/vector_index_system/README.md)
- [前端](../frontend/README.md)
- [脚本](../scripts/README.md)
- [结构化数据](../structured/README.md)
- [数据目录](../data/README.md)
- [第三方与引用说明](../THIRD_PARTY.md)

## 维护规则

- 改动用户可见行为时，同步更新对应模块文档。
- 改动单端口入口、Render 配置、端口、缓存策略或启动脚本时，同步更新 [单端口 FastAPI 版本](modules/single-port-fastapi.md)。
- 新增配置项时，同步更新 `.env.example` 和运行时配置文档。
- 新增外部服务、CDN、复制代码、数据集、论文或模型时，同步更新 `THIRD_PARTY.md`。
- 不在公开文档中写入 API Key、个人路径、未公开论文文件或本地参考材料。
- 运行时数据和生成文件必须继续留在 Git 之外。
- 前端资源版本号变更时，应能从提交说明或文档中看出原因。
