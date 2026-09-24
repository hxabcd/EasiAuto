# EasiAuto AI Agent Instructions

## 项目概述

- 项目名为 EasiAuto
- Windows 桌面应用，使用 `PySide6` + `qfluentwidgets` (Fluent Design)
- 为**希沃白板 (EasiNote)**提供自动登录，及通过 ClassIsland 自动触发登录任务

## 项目主要结构速览

```
main.py                  # 入口：调用 Launcher
src/EasiAuto/
  consts.py              # 路径常量、标识符
  cli.py                 # 命令行解析、凭据解析与子命令分发
  launcher.py            # 单实例协调、命令执行与登录流程生命周期
  core/                  # 无业务、无 UI 的基础设施，可被任意层引用
    display.py           # 缩放比例、屏幕尺寸与坐标换算
    process.py           # 进程终止与外部程序探测
    window.py            # 窗口查找与激活
    resources.py         # 只读资源路径
    diagnostics.py       # 运行环境诊断信息
    security.py          # 主密码派生、档案加密与账号脱敏
    qt_abc.py            # Qt 与 ABC 兼容元类
  runtime/               # 应用运行期机制（允许全局副作用与 UI 工具包依赖）
    exception_handler.py # 异常处理、日志与 Sentry
    lifecycle.py         # 退出、重启与退出信号处理
    elevation.py         # 按需管理员提权
    ipc.py               # 单实例互斥锁 + 主/次实例 argv 转发
    compatibility_patches.py  # 三方库兼容补丁
    refresh_animation.py # 刷新率驱动的动画实现（供补丁安装）
  models/                # 配置、档案的模型及单例
  services/              # 业务服务层：能力实现与编排
    announcement_service.py  # 公告轮询（单例 + 后台线程）
    update_service.py    # 版本更新检查与安装（单例 + 后台线程）
    binding/             # 档案与外部软件的科目绑定：base(契约) + 各后端（如 classisland.py）
    automation/          # 登录自动化：对外只用 automation_manager（包门面）；内部 manager(信号转发) + automator(四种方案)
  integrations/
    easinote/            # api(登录接口) / env(启动环境检测) / path(路径解析) /
                         # patcher(二进制修补) / pipe(命名管道协议) / process(进程控制)
    classisland/         # classisland(配置读写)
  view/                  # Qt 呈现层
    main_window.py       # 主窗口
    login_preflight.py   # 登录前置流程与临时 UI（横幅 / 状态浮窗 / 隐私遮罩）
    shortcuts.py         # 快捷方式创建与维护（含界面提示）
    notifications.py     # Windows 通知封装
    helpers.py           # UI 工具函数
    tokens.py            # 颜色与尺寸令牌
    components/
    pages/
    oobe/                # 首次设置向导
data/                    # 运行时数据
resources/               # 资源
tools/                   # 编译脚本、开发工具、发行中心
vendors/                 # 运行时依赖
```

## 分层约定

- `core/`：无业务概念、无 UI 工具包依赖、无全局副作用，可被任意层引用（`consts.py` 与之同级）
- `models/`：配置与档案的状态模型及单例；可依赖 `core/`
- `runtime/`：应用运行期机制（异常上报、退出与重启、提权、单实例 IPC、三方补丁），允许全局副作用与
  UI 工具包依赖；可被其上层使用，自身不依赖 `view/`、`services/`
- `integrations/`：外部系统/协议/二进制适配，不含业务策略
- `services/`：业务能力（公告轮询、版本更新、绑定同步、登录自动化），可编排 `integrations/` 与 `runtime/`
- `view/`：Qt 呈现层
- `cli.py`、`launcher.py`、`main.py`、包根 `__init__.py`：组合根，可依赖任意层

约束由 `tools/develop/check_layers.py` 按 import 图校验（`uv run python tools/develop/check_layers.py`）：
它区分「包内自引用」与「跨层引用」，因此 `services/` 这类含子包的层同样受约束；
新增顶层模块（或新的子层）需要在脚本的 `ALLOWED_LAYERS` 中登记，否则检查会报「未登记的分层」。

包内约定：对外接口由包的 `__init__.py` 门面导出（如 `from EasiAuto.services.automation import automation_manager`），
调用方不直接引用包内模块路径；包内相互引用使用相对导入（如 `from .automator import ...`）。

## 编码规范

- **语言**：注释、日志、UI 文本一律使用**简体中文**
- **代码风格**：使用 Python 3.12 风格
- **Docstring**：简单函数不需要；复杂函数需说明参数、返回值、可能异常
- **标记**：`TODO` 标记待完成，`NOTE` 标记需特别注意

## 注意事项

- 修改工作区时（如新增代码、提交），尽量与已有的内容风格上保持一致
- 需求不明确时，倾向于向用户确认而非直接修改
- 使用 uv 运行环境相关的代码
