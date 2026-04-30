# 数据与资料模块

数据与资料模块覆盖 `structured/`、`data/`、`backend/data/`、`.runtime/`、论文资料和第三方来源说明。该模块决定哪些数据可以提交，哪些只能作为本地运行产物存在。

## 目录说明

| 路径 | 内容 | 默认提交策略 |
| --- | --- | --- |
| `structured/` | 结构化教材章节、公式库、表格库 | 可提交，但需要确认来源许可 |
| `data/` | 本地知识图谱数据库或实验数据 | 数据库默认不提交 |
| `backend/data/` | 后端运行数据、章节缓存、教师端图谱包 | 视来源决定，默认谨慎提交 |
| `.runtime/` | 启动器日志、进程文件、截图、浏览器临时目录 | 不提交 |
| `WWW26_GLOW__Copy_.pdf` | 原始论文资料，本地参考文件 | 默认不提交；公开前确认再分发权利 |
| `GC-DPG参考.md` | KG 约束学习流程参考说明 | 可提交 |
| `THIRD_PARTY.md` | 第三方来源、仓库、论文和许可证记录 | 必须随项目维护 |

## structured 数据

`structured/` 当前包含：

- `chapter6_001.json` 到 `chapter6_022.json`
- `formula_library.json`
- `table_library.json`

维护 API 可通过 `POST /api/maintenance/scan-structured` 扫描这些文件，并生成图谱节点、关系和教师端包。

结构化数据的常见用途：

- 为授课文案生成提供章节证据；
- 为题库生成提供可引用知识点；
- 为图谱管理页提供节点和关系；
- 为学生端学习路径提供前置和后续知识。

## 后端运行数据

| 文件 | 来源 | 用途 |
| --- | --- | --- |
| `backend/data/chapters.json` | 教育 API 保存或生成 | 章节、授课文案、题库缓存 |
| `backend/data/structured_sync_manifest.json` | 维护 API 同步生成 | 记录结构化文件 hash 和同步结果 |
| `backend/data/teacher_memory_package.json` | 维护 API 导出生成 | 教师端图谱包和前端缓存 |

如果这些文件包含受限教材、第三方论文内容或真实教学数据，公开前应移除或替换为脱敏示例。

## 本地数据库和索引

默认忽略以下文件类型：

- `*.db`
- `*.sqlite`
- `*.sqlite3`
- `*.faiss`
- `*.index`
- `*.pkl`
- `*.pickle`

原因是这些文件通常是运行期产物、体积较大，且可能包含未脱敏内容。

## 论文和外部资料

`WWW26_GLOW__Copy_.pdf` 是项目本地参考资料。公开仓库时，应确认是否有权再分发 PDF。当前 `.gitignore` 默认排除 PDF；若没有明确再分发权利，应只在 `THIRD_PARTY.md` 中记录论文官方链接或 DOI。

`GC-DPG参考.md` 是对项目约束生成策略的本地参考说明，核心思想已体现在 `backend/education/kg_constraints.py`。

## 发布检查

公开或提交前，应检查：

- `structured/` 是否包含不可再分发教材内容；
- `backend/data/` 是否包含真实学生、教师或课堂数据；
- `.runtime/` 是否已被忽略且未暂存；
- 数据库和索引文件是否未进入 Git；
- `THIRD_PARTY.md` 是否列出所有外部来源；
- 论文 PDF 是否允许随仓库分发。

## 新增数据规则

新增数据文件时，应优先选择可审阅的 JSON、CSV 或 Markdown。二进制数据库、模型和索引只在确有必要时提交，并且需要在 README 或数据文档中解释来源、生成方式、许可证和更新流程。
