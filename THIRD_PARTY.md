# Third-Party Notices

本文件记录 Knowledge-Gragph-Teaching-System 中直接或间接使用、参考、调用的第三方资源。公开发布、提交作业或部署前，应逐项确认许可证、使用范围和是否需要保留版权声明。

## 为什么要单列第三方链接

如果项目使用了别人的仓库、源码、论文、模型、数据集、图片、字体、CDN 库或算法实现，建议单独列出：

- 名称
- 链接
- 用途
- 许可证或使用条款
- 是否随本仓库再分发
- 本项目是否做了修改

这不是单纯的格式问题，而是为了明确归属、方便许可证检查，也避免以后项目公开时无法追踪外部来源。

## Direct Runtime Services

| 名称 | 链接 | 用途 | 是否随仓库分发 | 备注 |
| --- | --- | --- | --- | --- |
| DeepSeek API | https://platform.deepseek.com/ | 问答、授课文案、题库生成 | 否 | 通过用户配置的 API key 调用；模型由 `.env` 中的 `DEEPSEEK_FLASH_MODEL` 和 `DEEPSEEK_PRO_MODEL` 控制。 |

## Frontend Libraries Loaded by CDN

| 名称 | 链接 | 用途 | 是否随仓库分发 | 许可证检查 |
| --- | --- | --- | --- | --- |
| KaTeX | https://github.com/KaTeX/KaTeX | 数学公式渲染 | 否，CDN 加载 | 发布前确认版本许可证。 |
| vis-network | https://github.com/visjs/vis-network | 教师端知识图谱可视化 | 否，CDN 加载 | 发布前确认版本许可证。 |
| Cytoscape.js | https://github.com/cytoscape/cytoscape.js | 图谱查看页可视化 | 否，CDN 加载 | 发布前确认版本许可证。 |
| cytoscape-fcose | https://github.com/iVis-at-Bilkent/cytoscape.js-fcose | Cytoscape 布局插件 | 否，CDN 加载 | 发布前确认版本许可证。 |
| cytoscape-dagre | https://github.com/cytoscape/cytoscape.js-dagre | Cytoscape 布局插件 | 否，CDN 加载 | 发布前确认版本许可证。 |
| D3.js | https://github.com/d3/d3 | 后端图谱管理页可视化 | 否，CDN 加载 | 发布前确认版本许可证。 |

## Research / Local Reference Repositories

以下目录或配置中出现过相关名称，但当前根目录 `.gitignore` 已默认排除大型第三方/研究系统目录。若后续决定把这些代码纳入仓库，需要补充具体版本、来源、许可证和改动说明。

| 名称 | 链接 | 项目中用途 | 当前处理 |
| --- | --- | --- | --- |
| mem0 | https://github.com/mem0ai/mem0 | 记忆系统参考或本地实验目录 | `backend/vector_index_system/memory_systems/` 默认忽略。 |
| Microsoft GraphRAG | https://github.com/microsoft/graphrag | GraphRAG 相关研究/实验参考 | `backend/vector_index_system/memory_systems/` 默认忽略。 |
| OpenClaw / Engram | https://github.com/openclaw | 记忆/代理系统参考目录 | `backend/vector_index_system/memory_systems/` 默认忽略；请按实际来源补充准确链接。 |

## Papers and Project References

| 名称 | 文件/链接 | 用途 | 备注 |
| --- | --- | --- | --- |
| WWW26_GLOW__Copy_.pdf | 本地文件，默认由 `.gitignore` 排除 | 原始论文资料 | 未确认再分发权利前不随公开仓库提交；建议改为记录论文链接或 DOI。 |
| GC-DPG 参考说明 | `GC-DPG参考.md` | 将 GC-DPG 思路泛化为交互式学习流程 | 本地参考文档。 |

## Assets and Data

| 名称 | 路径 | 用途 | 备注 |
| --- | --- | --- | --- |
| 结构化章节数据 | `structured/` | 教材章节、公式、表格数据 | 公开前确认原始教材/论文/数据来源是否允许再分发。 |
| 知识图谱数据库与运行期缓存 | `.runtime/`, `backend/data/`, `data/` | 本地运行数据 | 默认不提交。 |
| 本地模型文件 | `backend/vector_index_system/models/` | 向量/嵌入模型 | 默认不提交；如分发需单独列模型许可证。 |

## Attribution Checklist

发布或提交前逐项检查：

- [ ] 是否直接复制过第三方仓库代码。
- [ ] 是否修改过第三方代码。
- [ ] 是否包含第三方论文 PDF、教材内容、图片、模型或数据集。
- [ ] 是否已记录每个外部来源的链接。
- [ ] 是否已确认许可证允许当前使用方式。
- [ ] 是否需要在 README、LICENSE 或 NOTICE 中保留版权声明。
- [ ] 是否应改为只提供外部链接，而不是把原文件放进仓库。

## 推荐记录格式

```text
名称：
链接：
版本或提交号：
用途：
许可证：
是否随本仓库分发：
是否做过修改：
备注：
```
