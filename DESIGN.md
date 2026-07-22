# Design System

## Direction

一键游采用清爽、自然、可信的移动旅行产品风格。界面优先呈现真实旅行场景与可执行信息，不使用传统 OTA 的密集促销样式，也不使用装饰性科技感。

## Color

- Canvas: `oklch(0.975 0.008 145)`
- Surface: `oklch(0.995 0.004 145)`
- Ink: `oklch(0.235 0.025 155)`
- Muted ink: `oklch(0.52 0.025 155)`
- Primary: `oklch(0.61 0.13 164)`
- Primary dark: `oklch(0.43 0.095 164)`
- Coral action: `oklch(0.69 0.17 35)`
- Sun status: `oklch(0.84 0.15 88)`
- Border: `oklch(0.9 0.012 155)`
- Error: `oklch(0.58 0.18 28)`

主色只用于关键操作、当前选择和进度状态。珊瑚橙用于预订与费用相关操作，不作为大面积装饰。

## Typography

使用系统中文无衬线字体栈：`-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`。正文 14px 到 15px，关键页面标题 24px 到 30px，标签与辅助数据 11px 到 13px。字间距固定为 0。

## Shape And Elevation

- 普通控件圆角 10px 到 12px
- 主要内容卡片圆角 16px
- 图片卡片圆角 18px
- 头像与图标按钮使用圆形
- 阴影只用于浮动输入栏、底部导航和高优先级内容，普通信息使用边框或留白分组

## Components

- 顶部栏：56px 高，标题居中或左对齐，返回与操作均为图标按钮
- 底部导航：四个核心入口，使用 Element Plus 线性图标和短标签
- AI 输入栏：大面积文本输入加圆形发送按钮，可附带当前位置入口
- 标签：用于偏好选择时为轻量矩形选项，选中态同时改变背景、文字与勾选图标
- 行程时间线：时间、活动、交通耗时与费用形成稳定四层层级
- 预订操作：在行程项内展开，不使用打断流程的居中弹窗

## Motion

交互反馈使用 160ms 到 220ms 的 ease-out 过渡。只动画透明度与 transform。尊重 `prefers-reduced-motion`，关闭非必要位移动画。

## Responsive Behavior

移动端占满 `100dvh` 并保证每个页面独立滚动。桌面端以 430px 宽的移动应用预览展示，最大高度 900px。所有触控目标最小 44px，长地名和按钮文字允许换行。
