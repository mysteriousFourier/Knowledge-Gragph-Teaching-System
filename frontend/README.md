# 前端

`frontend/` 是 KGTS 的 React + Vite 前端，负责统一承载教师端、学生端、知识图谱浏览页和图谱管理入口。后端 API 不在这个目录实现，开发时通过 Vite 代理访问根目录的 Python 服务。

## 技术栈

- React 19
- TypeScript
- Vite 6
- TanStack Router
- TanStack Query
- Redux Toolkit
- Tailwind CSS

## 本地开发

安装依赖：

```bash
npm install
```

启动前端开发服务器：

```bash
npm run dev
```

默认地址是 `http://127.0.0.1:3000/`。

开发服务器会把下面两个路径代理到后端：

- `/api`
- `/env-config.js`

默认代理目标：

```bash
http://127.0.0.1:8000
```

如需修改：

```bash
VITE_DEV_API_TARGET=http://127.0.0.1:8000
```

## 生产构建

```bash
npm run build
```

构建产物输出到 `frontend/dist/`，由仓库根目录的 `render_app.py` 直接托管。

## 目录结构

```text
src/
  api/              Axios 客户端与接口封装
  components/       通用组件、布局、渲染器、视觉效果
  hooks/            自定义 hooks
  lib/              运行时配置、常量、工具函数
  routes/           TanStack Router 路由页面
  store/            Redux store 与切片
  types/            前端类型定义
```

## 运行时配置

前端不会把 API 地址写死在构建产物里，而是从 `/env-config.js` 读取运行时配置：

- `educationApiBaseUrl`
- `maintenanceApiBaseUrl`
- `backendAdminBaseUrl`

根目录的 `render_app.py` 和旧的 `backend/start_all.py` 都会生成或注入这份配置。

## 页面范围

- `/login`
- `/teacher/*`
- `/student/*`
- `/graph`
- `/graph/admin`

## 当前交互约定

- 教师端题库页面每次生成 5 道新题，总题库不设置上限
- 教师点踩的题目会从学生练习中排除
- 学生练习每次进入或重新开始时随机抽取最多 10 题
- 题目选项使用统一的选项标签渲染，避免出现 `A. A.`、`B. B.` 这类重复前缀
- Markdown / LaTeX 内容通过公共渲染器展示，选项内公式也会渲染

## 移动端适配

前端已针对窄屏设备做基础适配：

- 手机端优先显示实际工作区，左侧图谱装饰区会压缩为顶部上下文区域
- 顶部导航和底部快捷入口支持横向滑动
- 教师题库、学生练习、学习、复习、PPT、授课、图谱和图谱管理页面会在窄屏下换行为单列或满宽按钮
- 长公式、表格和代码块会横向滚动，避免撑破页面

## 维护约定

- 路由变更优先查看 `src/routes/`
- API 地址和认证拦截逻辑集中在 `src/api/`
- 如果调整了后端返回结构，通常还需要同步修改 `src/types/` 和页面层的数据读取逻辑
- 不要在前端 API 客户端里给 DeepSeek 生成请求加短超时；生成接口可能因为并发和模型响应慢而需要等待
