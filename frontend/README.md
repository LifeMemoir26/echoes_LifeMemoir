# Frontend

## 启动

```bash
pnpm install
pnpm run dev        # http://localhost:3000
```

代码默认使用相对路径 `/api/v1`，由 `next.config.ts` 中的 rewrites 代理到 `http://127.0.0.1:8000/api/v1`。如需指向其他后端地址，可通过环境变量覆盖：

```bash
# .env.local（可选）
NEXT_PUBLIC_API_BASE_URL=http://your-backend:8000/api/v1
```

## 路由架构

基于 Next.js 16 App Router，使用 Route Group 区分认证区域：

```
app/
├── layout.tsx              # 根 layout（QueryClientProvider）
├── providers.tsx           # React Query provider
├── globals.css             # 全局样式 + Tailwind
├── login/page.tsx          # 登录页（无导航）
├── register/page.tsx       # 注册页（无导航）
└── (app)/                  # 认证后路由组
    ├── layout.tsx          # AuthGuard + AppNav 导航
    ├── page.tsx            # / 首页（Dashboard）
    ├── interview/page.tsx  # 采访页
    ├── knowledge/
    │   ├── page.tsx        # 知识管理页
    │   ├── events/page.tsx # 事件浏览页
    │   └── profile/page.tsx  # 人物侧写页
    ├── timeline/page.tsx   # 时间线页
    └── memoir/page.tsx     # 回忆录页
```

`(app)/layout.tsx` 统一包含 `<AuthGuard>` 和 `<AppNav>`，认证后页面无需单独包裹。

## 组件结构

```
components/
├── auth/                   # 登录/注册页面组件
├── dashboard/              # 首页仪表盘
├── interview/              # 采访相关面板
│   ├── interview-page.tsx  # 主页面（含 SSE 对话）
│   ├── voice-record-panel  # 语音录入面板
│   ├── pending-events-panel
│   ├── emotional-anchors-panel
│   └── background-supplement-panel
├── knowledge/              # 知识管理（上传 + 浏览）
│   ├── knowledge-page.tsx  # 素材管理主页面
│   ├── events-page.tsx     # 事件浏览页面
│   └── profile-page.tsx    # 人物侧写页面
├── memoir/                 # 回忆录展示
├── timeline/               # 时间线展示
├── layout/                 # 导航栏（AppNav）+ 页面过渡动画
└── ui/                     # 基础 UI 组件
    ├── button.tsx
    ├── card.tsx
    ├── input.tsx
    ├── status-badge.tsx
    ├── error-banner.tsx
    └── magnetic-hover.tsx
```

## 设计系统

暖棕色调主色方案，定义在 [styles/tokens.css](styles/tokens.css)：

| Token            | 值                                  | 用途           |
| ---------------- | ----------------------------------- | -------------- |
| `--accent`       | `#A2845E`                           | 主色           |
| `--accent-light` | `#F5EDE4`                           | 浅底色         |
| `--accent-mid`   | `#C4A882`                           | 边框色         |
| `--focus-ring`   | `0 0 0 3px rgba(162, 132, 94, 0.3)` | 焦点环         |

Card 材质：`bg-white/80 backdrop-blur-sm border border-black/[0.06]`

页面背景渐变：`radial-gradient(circle at top, #FDF6EE 0%, #fafaf8 45%, #fafaf8 100%)`

面板标签样式：`text-xs uppercase tracking-[0.16em] text-[#A2845E]`

## 常用命令

```bash
pnpm run dev              # 开发服务器
pnpm run build            # 生产构建
pnpm run typecheck        # TypeScript 类型检查
pnpm run test:unit        # Vitest 单元测试
pnpm run lint             # ESLint 检查
pnpm run check:contract   # API 契约一致性检查
```
