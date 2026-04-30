# 教育 API 模块

教育 API 位于 `backend/education/`，默认运行在 `http://127.0.0.1:8001`。该模块服务教师端和学生端业务流程，负责授课文案生成、问答、题库、学习路径和 KG 约束检查。

## 主要文件

| 文件 | 职责 |
| --- | --- |
| `api_server.py` | FastAPI 入口，定义教师端、学生端和教育生成接口 |
| `claude_api.py` | DeepSeek API 客户端，按任务选择 flash/pro 模型 |
| `kg_constraints.py` | `LearningPlan`、证据约束、生成一致性检查 |
| `vector_backend_bridge.py` | 对接图谱与向量模块，构建前端图谱和 RAG 上下文 |
| `exercise_generator.py` | 练习题生成和答案检查逻辑 |
| `lecture_generator.py` | 授课文案生成逻辑 |
| `qa_generator.py` | 问答生成逻辑 |
| `knowledge_path.py` | 前置知识、后续知识、学习路径 |
| `data_organizer.py` | 将图谱和章节数据整理为前端结构 |
| `edu_config.py` | 题型数量等教育参数 |

## 模型分流

| 任务 | 模型变量 | 说明 |
| --- | --- | --- |
| 学生问答 | `DEEPSEEK_FLASH_MODEL` | 低延迟回答，优先图谱证据 |
| 教师端问答兜底 | `DEEPSEEK_FLASH_MODEL` | 用于快速解释和补充 |
| 授课文案生成 | `DEEPSEEK_PRO_MODEL` | 深度生成，要求结构化输出 |
| 自然补充 | `DEEPSEEK_PRO_MODEL` | 将教师补充内容转为图谱约束材料 |
| 题库生成 | `DEEPSEEK_PRO_MODEL` | 生成可复用题库并缓存 |

## KG 约束流程

```text
用户请求
  -> 图谱检索 / 向量检索 / 章节缓存
  -> 构建 evidence 和 relation evidence
  -> build_learning_plan()
  -> build_constrained_generation_prompt()
  -> DeepSeek 生成
  -> check_generation_consistency()
  -> 返回内容 + learning_plan + consistency_report
```

系统应遵循以下规则：

- 图谱证据不足时返回明确提示，不用模型常识补全为确定事实。
- 生成内容只应引用 `LearningPlan` 中允许使用的知识点和关系。
- 练习题必须保留标准答案、解析、证据和题目 ID。
- 教师端生成内容需要保留 `consistency_report`，便于人工审核。

## 主要接口

### 通用接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/` | 服务信息 |
| `GET` | `/api/health` | 健康检查 |

### 教育生成

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/education/generate-lecture` | 基于章节和图谱生成授课文案 |
| `POST` | `/api/education/ask-question` | 教师端或通用问答 |
| `POST` | `/api/education/learning-plan` | 单独生成学习计划 |
| `POST` | `/api/education/natural-supplement` | 解析教师自然语言补充 |

### 图谱与章节

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/education/graph` | 获取前端图谱数据 |
| `POST` | `/api/education/add-node` | 添加图谱节点 |
| `PUT` | `/api/education/update-node` | 更新图谱节点 |
| `GET` | `/api/education/search-nodes` | 搜索图谱节点 |
| `GET` | `/api/education/schema` | 获取图谱 schema |
| `POST` | `/api/education/save-chapter` | 保存章节内容 |
| `GET` | `/api/education/list-chapters` | 列出章节 |
| `GET` | `/api/education/get-chapter` | 获取章节详情 |
| `POST` | `/api/education/save-lecture` | 保存授课文案 |

### 登录与学生学习

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/teacher/login` | 教师登录 |
| `POST` | `/api/student/login` | 学生登录 |
| `GET` | `/api/student/chapter` | 获取学生当前章节 |
| `POST` | `/api/student/mark-chapter` | 标记章节学习状态 |
| `POST` | `/api/student/generate-exercises` | 生成或预创建题库 |
| `GET` | `/api/student/exercises` | 获取章节题库 |
| `POST` | `/api/student/question` | 学生问答 |
| `GET` | `/api/student/review` | 获取复习内容 |
| `POST` | `/api/student/check-answer` | 检查学生答案 |
| `POST` | `/api/student/learning-path` | 生成学习路径 |
| `GET` | `/api/student/prerequisites` | 查询前置知识 |
| `GET` | `/api/student/follow-up` | 查询后续知识 |

## 题库缓存

题库生成后写入章节数据，前端优先读取缓存：

```text
backend/data/chapters.json
  -> .runtime/chapters.json 或前端章节缓存
  -> frontend/chapters-cache.json
  -> student.html
```

题目结构应包含：

- `id`
- `type`
- `question`
- `options`
- `answer`
- `explanation`
- `evidence`
- `knowledge_points`

## 错误处理

- `DEEPSEEK_API_KEY` 缺失时，生成类接口应返回可读错误。
- 教师或学生密码未配置时，登录接口应拒绝登录。
- 图谱模块不可用时，教育接口应降级返回本地章节缓存或明确错误。
- 题库缓存写入失败时，应返回题目但提示缓存状态。

## 扩展规则

新增教育功能时，应优先复用 `kg_constraints.py` 中的计划、证据和一致性检查逻辑。新增学生端或教师端 API 后，需要同步更新 [前端模块](frontend.md) 与本文档。
