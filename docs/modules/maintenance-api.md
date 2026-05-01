# 维护 API 模块

维护 API 位于 `backend/maintenance/`，默认端口为 `8002`。它负责知识图谱数据的维护、同步和导出。

在单端口 FastAPI 模式下，维护 API 由 `render_app.py` 挂到同一个 Web Service，前端通过同源 `/api/maintenance/...` 访问，不再需要浏览器跨端口请求 `8002`。

## 主要职责

- 查询图谱节点。
- 查询图谱关系。
- 新增、更新、删除节点。
- 新增、更新、删除关系。
- 从结构化数据同步章节、公式和表格。
- 导出图谱。
- 为前端提供可渲染的节点详情。

## 关键文件

| 文件 | 职责 |
| --- | --- |
| `api_server.py` | 路由、请求校验、图谱操作 |
| `structured_sync.py` | 结构化材料同步 |

## 节点详情

图谱右侧详情需要返回可渲染文本。字段中如果包含 Markdown 或 LaTeX，前端会继续渲染。维护 API 应尽量在返回前展开公式引用，尤其是：

```text
[[FORMULA:...]]
[[SEE_FORMULA:...]]
Equation ...
```

## 结构化同步

同步流程应读取：

- 章节结构化文件。
- `structured/formula_library.json`。
- `structured/table_library.json`。

同步结果应保留原始知识文本和必要元数据。对于课程原文，优先保留英文。

`render_app.py` 会在启动时检查图谱节点数量。若节点数量低于 `RENDER_AUTO_SYNC_MIN_NODES`，且 `RENDER_AUTO_SYNC_STRUCTURED` 未关闭，会自动调用结构化同步，避免新部署环境中图谱为空或只有单个节点。

## 数据安全

维护 API 不应暴露：

- `.env` 内容。
- API Key。
- 本地绝对个人路径。
- 未公开论文文件。
- 本地模型路径。

## 与前端的契约

前端依赖维护 API 返回：

- 节点 ID。
- 节点标题。
- 节点类型。
- 节点正文或描述。
- 关系列表。
- 公式、表格和来源信息。

改字段名或结构时，需要同步修改前端图谱页面、教师端和学生端。
