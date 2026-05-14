# 维护 API 兼容入口

`backend/maintenance/` 是图谱维护 API 的兼容入口目录。当前主逻辑已经集中在仓库根目录的 `maintenance/` 包。

## 运行模式

### 单端口模式

根目录 `render_app.py` 会把维护接口挂到同一个 Web 服务中，路径前缀为：

```text
/api/maintenance/*
```

### 拆分服务模式

如果要单独启动维护 API：

```bash
python backend/maintenance/api_server.py
```

默认端口是 `8002`。

## 关键文件

| 文件 | 作用 |
| --- | --- |
| `backend/maintenance/api_server.py` | FastAPI 兼容启动入口 |
| `maintenance/router.py` | 维护 API 主路由 |
| `maintenance/graph_ops.py` | 节点与关系的图操作 |
| `maintenance/import_export.py` | 导入导出 Graph / GraphML / 教师包 |
| `maintenance/structured_sync.py` | 把 `structured/` 同步进知识图谱 |
| `maintenance/analytics.py` | 图谱统计与审计 |

## 能力范围

- 节点和关系增删改查
- 图谱搜索与语义搜索
- GraphML / JSON / SQLite 导入
- 图谱导出与教师包导出
- 结构化数据同步
- 图谱校验、孤立节点清理、关系审计
- 子图、前置知识、后续知识查询

## 维护约定

- 主逻辑改动优先落在根目录 `maintenance/`
- 同步 `structured/` 前先确认数据允许公开或允许本地使用
- 涉及字段名调整时，需要联动前端图谱页和教学侧桥接逻辑
