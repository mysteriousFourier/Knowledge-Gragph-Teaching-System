# Maintenance API Module

`backend/maintenance/` 是后台维护 API 模块，负责知识图谱节点关系维护、结构化数据同步、GraphML 导入、图谱导出、校验和统计。

## 核心能力

- 添加、更新和删除图谱节点。
- 添加、更新和查询节点关系。
- 搜索、语义搜索和图谱结构查询。
- 扫描 `structured/` 并同步到图谱。
- 导入 GraphML，导出图谱和教师端数据包。
- 校验图谱结构并清理孤立节点。

## 主要入口

```powershell
python backend\maintenance\api_server.py
```

默认地址：

```text
http://127.0.0.1:8002/docs
```

## 详细文档

完整说明见 [docs/modules/maintenance-api.md](../../docs/modules/maintenance-api.md)。
