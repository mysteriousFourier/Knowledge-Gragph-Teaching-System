# MCP Server Module

`backend/mcp-server/` 提供知识图谱 MCP 工具桥接。项目主业务路径优先使用教育 API、维护 API 和 `backend/vector_index_system/`，本模块主要用于外部 MCP 客户端接入和兼容工具调用。

## 核心能力

- 暴露图谱读取、搜索、更新和路径查询工具。
- 支持 GraphML 解析和批量导入。
- 提供本地 MCP 数据目录和配置示例。

## 数据注意事项

`data/` 下的数据库和运行期文件默认不提交。公开分发前，应确认示例数据和第三方来源许可证。

## 详细文档

完整说明见 [docs/modules/mcp-server.md](../../docs/modules/mcp-server.md)。
