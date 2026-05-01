# 第三方与引用说明

本文档记录项目中使用、参考或需要声明的外部资源。这样做不是单纯的格式要求，而是为了明确归属、方便许可证检查，并避免项目公开后无法追踪外部来源。

若后续引入新的服务、库、模型、数据集、论文或仓库，应同步更新本文件。

## 直接运行时服务

| 名称 | 链接 | 用途 | 是否随仓库分发 | 备注 |
| --- | --- | --- | --- | --- |
| DeepSeek API | https://platform.deepseek.com/ | 问答、授课文案、题库生成 | 否 | 通过用户配置的 API Key 调用；模型由 `.env` 中的 `DEEPSEEK_FLASH_MODEL` 和 `DEEPSEEK_PRO_MODEL` 控制 |

默认模型配置：

```env
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
DEEPSEEK_PRO_MODEL=deepseek-v4-pro
```

## 前端 CDN 库

前端是纯静态 HTML、CSS 和 JavaScript。若页面通过 CDN 或本地文件使用下列库，应在对应页面或脚本中保留来源说明。

当前主页 `index.html` 不再加载远程 CDN，以免入口动效被外部网络阻塞。教师端、学生端、图谱查看页和图谱后台仍可能按功能需要加载公式或图谱可视化库。

| 名称 | 链接 | 用途 | 是否随仓库分发 | 检查要求 |
| --- | --- | --- | --- | --- |
| KaTeX | https://github.com/KaTeX/KaTeX | LaTeX 公式渲染 | 否，CDN 加载或本地引用 | 发布前确认版本许可证 |
| vis-network | https://github.com/visjs/vis-network | 教师端知识图谱可视化 | 否，CDN 加载 | 发布前确认版本许可证 |
| Cytoscape.js | https://github.com/cytoscape/cytoscape.js | 图谱查看页可视化 | 否，CDN 加载 | 发布前确认版本许可证 |
| cytoscape-fcose | https://github.com/iVis-at-Bilkent/cytoscape.js-fcose | Cytoscape 布局插件 | 否，CDN 加载 | 发布前确认版本许可证 |
| dagre | https://github.com/dagrejs/dagre | 图布局算法 | 否，CDN 加载 | 发布前确认版本许可证 |
| cytoscape-dagre | https://github.com/cytoscape/cytoscape.js-dagre | Cytoscape 布局插件 | 否，CDN 加载 | 发布前确认版本许可证 |

Markdown 渲染当前由项目内置的 `frontend/markdown-renderer.js` 实现，不依赖 Marked。

KaTeX 在部分页面配置了 unpkg、jsDelivr 或 cdnjs fallback；这些 fallback 只用于运行时加载，不随仓库分发。

## 参考仓库

下列公开仓库可能作为设计思路、实验目录或对照参考。除非代码中明确复制了文件，否则它们不是本项目的运行时依赖。

| 名称 | 链接 | 项目中用途 | 当前处理 |
| --- | --- | --- | --- |
| mem0 | https://github.com/mem0ai/mem0 | 记忆系统参考或本地实验目录 | `backend/vector_index_system/memory_systems/` 默认忽略 |
| Microsoft GraphRAG | https://github.com/microsoft/graphrag | GraphRAG 相关研究或实验参考 | `backend/vector_index_system/memory_systems/` 默认忽略 |
| OpenClaw / Engram | https://github.com/openclaw | 记忆/代理系统参考目录 | `backend/vector_index_system/memory_systems/` 默认忽略；若实际来源不同，应补充准确链接 |

如果后续决定把第三方代码纳入仓库，必须补充具体版本、提交号、来源链接、许可证和本项目改动说明。

## 资产与数据

| 名称 | 路径 | 用途 | 备注 |
| --- | --- | --- | --- |
| 结构化章节数据 | `structured/` | 教材章节、公式、表格数据 | 公开前确认原始教材、论文或数据来源是否允许再分发 |
| 知识图谱数据库与运行时缓存 | `.runtime/`、`backend/data/`、`data/` | 本地运行数据 | 默认不提交 |
| 本地模型文件 | `backend/vector_index_system/models/` | 向量或嵌入模型 | 默认不提交；如分发需单独列模型许可证 |

## 数据与论文

- `structured/` 中只应提交适合公开的结构化课程材料、公式库和表格库。
- 本地论文 PDF、未公开草稿、个人笔记和临时参考说明不应提交。
- 如果未来公开引用具体论文或数据集，需要在这里列出标题、作者、链接、许可证和使用范围。

## 归属检查清单

发布或提交前逐项检查：

- [ ] 是否直接复制过第三方仓库代码。
- [ ] 是否修改过第三方代码。
- [ ] 是否包含第三方论文 PDF、教材内容、图片、模型或数据集。
- [ ] 是否记录了每个外部来源的链接。
- [ ] 是否确认许可证允许当前使用方式。
- [ ] 是否需要在 README、LICENSE 或 NOTICE 中保留版权声明。
- [ ] 是否应改为只提供外部链接，而不是把原文件放进仓库。

推荐记录格式：

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

## 许可证

本项目使用 MIT License。第三方库、服务和数据仍受其各自许可证或服务条款约束。
