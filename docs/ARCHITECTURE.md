# EasiAuto 项目深度分析

## 项目核心架构理解

### A. ClassIsland 集成与依赖关系

#### 当前机制（分层触发模式）

1. **ClassIsland 作为顶层调度器** (不可更改)
   - ClassIsland 是课程表管理应用，具有自动化触发能力
   - EasiAuto 作为 ClassIsland 的自动化执行插件

2. **触发流程**:
   - ClassIsland 监听课程时间表事件（下一节课前N秒触发）
   - 触发时运行命令: `EasiAuto.exe login --id {automation_id}`
   - EasiAuto 执行登录，完成后退出

3. **关键集成点**:
   - `classisland_manager.py`: ClassIsland 配置文件读写管理
     - 管理 ClassIsland 的自动化配置 JSON
     - 监听 ClassIsland 运行状态（通过互斥锁）
     - 支持 ClassIsland v1 和 v2 版本

   - `services/binding_service.py`: ClassIsland 绑定同步逻辑
     - 将 EasiAuto 档案与 ClassIsland 科目绑定
     - 生成 ClassIsland 自动化配置对象
     - 规则: 下一节课为目标科目 AND 上一节课不是目标科目

   - 配置存储位置:
     - Settings.json: ClassIsland 全局设置
     - Profiles/{name}.json: 课程表数据 (Subjects 字段)
     - Config/Automations/{name}.json: 自动化规则

4. **当前依赖**:
   - ClassIsland 存在且配置正确时，自动化功能才能使用
   - EasiAuto 无法独立触发登录任务
   - 单向依赖: EasiAuto → ClassIsland (不依赖 EasiAuto)

---

### B. 自动化系统架构

#### 登录任务执行流程

```
Launcher (main entry)
├─ 参数解析 (ArgumentParser)
│  ├─ login: --id {automation_id} 或 --account/--password
│  ├─ settings: 打开 UI
│  └─ skip: 跳过下一次登录
│
├─ 单例检查 (check_singleton)
│  └─ 使用互斥锁确保仅一个实例运行
│  └─ 失败时尝试向已有实例转发参数 (IPC)
│
├─ IPC 服务器启动 (UI 命令需要)
│  └─ 使用 QLocalServer 接收参数转发
│
└─ AutomationManager 执行登录
   ├─ 根据 config.Login.Method 选择登录方案
   ├─ 创建对应 Automator 线程
   └─ 发送信号: started, successed, interrupted, failed
```

#### 四种登录方案 (LoginMethod)

1. **FIXED (固定位置)**: 最稳定、最快
   - 预设坐标点击各控件
   - EnableScaling: 自动根据分辨率调整坐标
   - 基准: 1920x1080 100% 缩放
   - 支持旧版 EasiNote 的"直接模式"（无需黑板界面）

2. **CV (图像识别)**: 不稳定、较快
   - 使用 OpenCV 识别控件图片
   - 图片存储: resources/EasiNoteUI/
   - 支持 1080p 和 4K (200% 缩放)
   - 依赖 cv2（full 版本）

3. **UIA (自动定位)**: 最稳定、较慢
   - 使用 pywinauto 的 UI Automation 接口
   - 直接查询控件属性而非坐标
   - 可能极慢（官方注明）

4. **INJECT (进程注入)**: 不稳定、最快
   - 使用 Snoop 注入器注入 DLL
   - ENLoginInjector.dll 直接调用登录 API
   - 实验性功能

#### AutomationManager

- 单例，管理当前运行的 Automator
- 信号: started, finished, successed, interrupted, failed, task_updated, progress_updated

---

### C. 配置与档案系统

#### 配置模型 (config.py)

- 基于 Pydantic，支持自动验证和自动保存
- 路径: `data/config.json`
- 层级结构:

  ```
  Config
  ├─ Login: LoginConfig (方案、超时、位置、EasiNote 路径)
  ├─ Warning: WarningConfig (确认弹窗)
  ├─ Banner: BannerConfig (警示横幅样式)
  ├─ StatusOverlay: StatusOverlayConfig (状态浮窗)
  ├─ App: AppConfig (主题、日志、遥测)
  ├─ ClassIsland: ClassIslandConfig (CI 路径、默认名称、提前时长)
  ├─ Update: UpdateConfig (更新策略)
  ├─ Debug: DebugConfig (调试选项)
  ├─ Internal: InternalConfig (内部状态)
  └─ Statistics: StatisticsConfig (使用统计)
  ```
  
#### 档案模型 (profile.py)

- 路径: `data/profile.json`
- `EasiAutomation`: 单条登录档案

  ```
  {
    id: UUID,
    account: str,
    password: str (加密存储),
    name: str (老师名/显示名),
    account_name: str (希沃白板用户名),
    avatar: bytes (希沃白板头像),
    enabled: bool
  }
  ```

- 密码加密: Fernet (对称加密), token 格式 `ea2${encrypted_data}`
- `Profile` 管理 automations 列表和加密状态

---

### D. UI 架构

#### 页面导航 (main_window.py)

- MSFluentWindow (qfluentwidgets)
- 5 个页面:
  1. **ConfigPage**: 设置（Login, Warning, Banner, StatusOverlay, App）
  2. **ProfilePage**: 档案管理（添加、编辑、删除）
  3. **AutomationPage**: ClassIsland 绑定
  4. **UpdatePage**: 更新检查
  5. **AboutPage**: 关于

#### AutomationPage 架构

```
AutomationPage
├─ StatusBar: ClassIsland 连接状态显示 + 刷新 + 高级选项
├─ StackedWidget: 根据状态切换页面
│  ├─ PathSelectSubpage: 未检测到 CI 路径，提示下载/选择
│  ├─ CiRunningWarnOverlay: CI 正在运行，提示关闭
│  └─ BindingPage: 科目与档案绑定编辑
│     ├─ 左侧: 科目卡片 (已绑定/未绑定分组)
│     └─ 右侧: 档案卡片 (选择绑定)
│
└─ 状态监听 (QTimer 200ms 轮询):
   ├─ CI 未初始化 → 显示 PathSelectSubpage
   ├─ CI 正在运行 → 显示 CiRunningWarnOverlay
   └─ CI 未运行 → 显示 BindingPage
```

#### BindingPage 逻辑

- **数据流**:
  1. 读取 CI 科目列表 (`list_subjects()`)
  2. 读取 CI 当前绑定映射 (`get_binding_map()`)
  3. 用户编辑绑定
  4. 调用 `sync()` 写回 CI 配置

- **卡片复用优化**: 不销毁重建，仅隐藏/显示和重排

---

### E. 启动流程 (launcher.py + main.py)

#### 应用启动链路

1. **main.py**: 调用 `Launcher().run()`

2. **Launcher.run()**:
   - 参数解析
   - 单例检查 → 如失败则转发 (IPC) 或退出
   - 启动 IPC 服务器 (仅 UI 命令)
   - 版本更新通知
   - 命令分发:
     - `login`: 执行 `_start_login()`
     - `settings`: 显示 MainWindow
     - `skip`: 设置 `SkipOnce` 标志
     - `None` (默认): 显示 MainWindow

3. **_start_login()** 流程:

   ```
   _start_login(args)
   ├─ 解析凭据 (_resolve_login_credentials)
   │  ├─ 若 --id: 从 profile 查询
   │  └─ 若 --account: 使用提供的账号/密码
   ├─ 显示确认弹窗 (PreRunPopup) 可延迟登录
   ├─ 显示警示横幅 (WarningBanner)
   ├─ 显示状态浮窗 (StatusOverlay)
   ├─ 调用 automation_manager.run(account, password)
   └─ 登录完成后:
      ├─ 关闭所有视觉反馈
      ├─ 可选: 检查更新
      └─ 从 IPC 触发时: 保持运行；否则退出
   ```

4. **IPC 处理**:
   - 次实例启动 → 尝试连接主实例 IPC 服务器
   - 若成功 → 转发 argv → 主实例处理 → 次实例退出
   - 若失败 → 检查 `check_singleton(focus_existing)`，若有已运行实例则退出

---

### F. 构建系统

#### 构建命令

```bash
uv run python tools/build.py --type full    # FULL 版 (含 OpenCV + Snoop)
uv run python tools/build.py --type lite    # LITE 版 (轻量，无 OpenCV)
```

- **编译器**：Nuitka（将 Python 编译为原生可执行文件）
- **输出**：`build/{full|lite}/main.dist/`
- **分发**：自动打包为 `EasiAuto_v{version}[_lite].zip`
- **LITE 版差异**：不复制 `vendors/` 目录

#### 环境要求

- **Python**：3.12+（`pyproject.toml` 强制）
- **包管理**：`uv`
- **平台**：仅 Windows（依赖 pywin32、pywinauto、Windows API）

---

### G. 单例、IPC 与进程管理

#### 单例保障 ([singleton.py](src/EasiAuto/core/runtime/singleton.py))

- **互斥锁**：Windows 命名互斥锁 `EasiAutoMutex` (`CreateMutex`)

#### IPC 参数转发 ([client.py/server.py](src/EasiAuto/core/ipc/))

- **协议**：Qt `QLocalServer` / `QLocalSocket`
- **消息格式**：JSON，`{"argv": ["login", "--id", "xxx"]}`
- **用途**：新实例将命令行参数转发给已有实例处理，然后自身退出

---

### H. 异常处理与遥测

#### Sentry 上报 ([exception_handler.py](src/EasiAuto/core/runtime/exception_handler.py))

- 自动上报未捕获异常到 Sentry（DSN 内置，可在 Debug 配置关闭）
- **调试上下文**：附带内存使用、线程数、版本号、Python 版本、平台信息
- **错误去重**：2 秒内重复异常被忽略（防消息框轰炸）
- **多重捕获**：`sys.excepthook`（全局异常）、Qt 信号异常、`print()` 重定向

#### 日志系统

- **库**：`loguru`
- **路径**：`data/logs/`（启动时自动创建）
- **级别**：DEBUG

---

### I. 密码加密 ([security.py](src/EasiAuto/core/security.py))

- **加密**：Fernet 对称加密（`cryptography` 库）
- **密钥**：存于 `data/profile.key`（Windows 隐藏属性），首次运行自动生成
- **缓存**：密钥内存缓存 (`KEY_CACHE`)，避免重复读取
- **令牌格式**：`ea2${encrypted_data}`（`ea2` 表示架构版本 2）
- ⚠️ **密钥丢失** = 所有已存密码永久无法解密

---

### J. 关键常量与环境判断 ([consts.py](src/EasiAuto/consts.py))

| 常量 | 含义 |
|------|------|
| `IS_DEV` | `"__compiled__" not in globals()` → 是否开发环境 |
| `IS_FULL` | 能否 `import cv2` → 是否 FULL 版 |
| `EA_BASEDIR` | 应用根目录（可执行文件所在目录） |
| `EA_DATADIR` | 运行时数据目录 (`data/`) |
| `CONFIG_PATH` | `data/config.json` |
| `PROFILE_PATH` | `data/profile.json` |
| `LOG_DIR` | `data/logs/` |
| `EA_RESDIR` | 资源目录 (`resources/`) |
| `VENDOR_PATH` | 注入器目录 (`vendors/`，自动加入 `sys.path`) |

> **启动迁移**：旧版数据（根目录 `config.json`、`logs/`）会自动迁移到 `data/` 目录。

---

## 注意事项

| 陷阱 | 说明 |
|------|------|
| **JSON 编辑** | `data/config.json`、`data/profile.json` 应通过 Pydantic API 修改，直接编辑可能导致数据不一致或丢失 |
| **密钥丢失** | `data/profile.key` 丢失 → 所有已存密码无法解密，无恢复手段 |
| **INJECT 方案** | 仅 FULL 版可用（依赖 `vendors/Snoop/`），LITE 版自动隐藏此选项 |
| **EasiNote 路径** | 优先从注册表 `HKLM\SOFTWARE\WOW6432Node\Seewo\EasiNote5\ExePath` 读取，找不到才用默认路径 |
| **FIXED 坐标** | 基准为 1920×1080 100% 缩放，若设备分辨率/缩放不同需启用 `EnableScaling` |
| **UI 线程** | Automator 在独立 QThread 运行，UI 更新必须通过 Qt Signal，否则崩溃 |
| **ClassIsland 路径** | 手动选择或自动检测，路径存储在 `config.ClassIsland.Path` |

---

## 关键代码位置

| 功能 | 文件 | 关键类/函数 |
|-----|-----|-----------|
| 启动入口 | `launcher.py` | `Launcher.run()`, `_start_login()` |
| 登录执行 | `automator/manager.py` | `AutomationManager` |
| 四种登录方案 | `automator/{fixed,cv,uia,inject}.py` | `FixedAutomator`, `CVAutomator`, `UIAAutomator`, `InjectAutomator` |
| CI 集成 | `integrations/classisland_manager.py` | `ClassIslandManager` |
| CI 绑定 | `services/binding_service.py` | `ClassIslandBindingBackend` |
| 配置存储 | `models/config.py` | `Config` (Pydantic), `ConfigModel` |
| 档案管理 | `models/profile.py` | `EasiAutomation`, `Profile` |
| 密码加密 | `core/security.py` | `encrypt_token`, `decrypt_token` |
| 常量定义 | `consts.py` | `IS_DEV`, `IS_FULL`, `CONFIG_PATH` 等 |
| 单例与 IPC | `core/runtime/singleton.py` + `core/ipc/{client,server}.py` | `check_singleton`, `ArgvIpcServer`, `send_argv_to_primary` |
| 异常处理 | `core/runtime/exception_handler.py` | `init_exception_handler` |
| UI 主窗口 | `view/main_window.py` | `MainWindow` (MSFluentWindow) |
| UI 自动化页 | `view/pages/automation_page.py` | `AutomationPage` |
| 构建脚本 | `tools/build.py` | Nuitka 编译与打包 |

---

## 技术栈总结

- **GUI**：PySide6 + qfluentwidgets (Fluent Design)
- **配置/数据模型**：Pydantic 2.x + JSON，自动验证与保存
- **自动化**：pyautogui, pywinauto (UIA), cv2 (OpenCV), Snoop 注入器 (C# DLL)
- **IPC**：Qt QLocalServer / QLocalSocket (JSON 消息)
- **日志/遥测**：loguru + Sentry SDK
- **加密**：cryptography (Fernet)
- **打包**：Nuitka → `.exe` + `.zip` 分发
- **包管理**：uv
- **平台**：Windows 10/11 x64 独占
