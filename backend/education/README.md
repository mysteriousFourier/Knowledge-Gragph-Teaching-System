# 教育 API

`backend/education/` 是教师端和学生端共用的业务后端，默认端口为 `8001`。它负责章节数据、授课文案、问答、练习题、题目反馈和知识图谱证据整合。

## 核心文件

| 文件 | 职责 |
| --- | --- |
| `api_server.py` | FastAPI 入口、路由、章节缓存、题库接口 |
| `claude_api.py` | DeepSeek 兼容调用、模型路由、生成提示词 |
| `lecture_generator.py` | 授课文案生成与章节材料组织 |
| `qa_generator.py` | 问答上下文整理 |
| `kg_constraints.py` | 图谱证据、公式展开、约束文本构造 |
| `vector_backend_bridge.py` | 教育 API 与图谱后端之间的桥接 |

## 模型路由

- 学生端和教师端问答使用 `DEEPSEEK_FLASH_MODEL`。
- 授课文案、题库生成、深度内容整理使用 `DEEPSEEK_PRO_MODEL`。
- API Key 从 `.env` 读取，前端设置页只展示配置来源，不再要求用户重复填写。

## 题库流程

1. 后端根据章节材料、图谱证据和已有反馈生成候选选择题。
2. 题目写入 `.runtime/chapters.json`。
3. 教师端可对题目整体和单个选项点赞/点踩。
4. 点赞题目保留到题库；点踩题目从候选题库移除。
5. “继续生成”会保留满意题目，并补充新的候选题。

当前反馈主要用于后续提示词约束和本地数据记录，不会自动训练神经网络。

## 渲染约定

API 返回给前端的文本允许包含 Markdown 和 LaTeX。公式编号会尽量从 `structured/formula_library.json` 展开，避免只显示 `Equation 6.35` 这样的占位文本。

更多细节见 [教育 API 模块文档](../../docs/modules/education-api.md)。
