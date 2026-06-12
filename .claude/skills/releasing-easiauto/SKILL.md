---
name: releasing-easiauto
description: Use when the user asks to publish a new EasiAuto version, create a release, bump the version, or prepare a changelog. Triggers on requests like "发布新版本", "release v1.2.3", "准备发版", or "写更新日志".
---

# EasiAuto 发版

## 概述

自动化 EasiAuto 版本发布流程：修改版本元数据 → 总结更新日志 → 推断元数据 → 用户审核 → 使用发行中心发布。

## 何时使用

- 用户说"发版""发布新版本""release"
- 用户提供了目标版本号并要求发布
- 用户要求准备更新日志

**不使用于**：仅修改代码不涉及发布、仅查看当前版本号。

## 流程

### 第零步：确保工作树干净且与远端同步

发版前**必须确保工作树无未提交的更改，且本地与远端同步**。

```bash
# 1. 检查工作树是否干净
git status --short

# 2. 检查远端是否有新提交
git fetch origin
git log HEAD..origin/$(git branch --show-current) --oneline
```

- 工作树有未提交更改 → 先处理（提交或暂存）
- 远端有新提交 → **告知用户，让用户自行处理**（pull/rebase），不要在发版流程中自动合并
- 两项检查均通过 → 继续发版

### 第一步：修改版本元数据并提交

1. 用户输入目标版本号（若未提供，先询问）
2. 同时修改两个文件中的版本号：
   - `src/EasiAuto/__init__.py`：`__version__ = "<新版本>"`
   - `pyproject.toml`：`[project]` 下的 `version = "<新版本>"`
3. 运行 `uv sync` 确保锁定文件同步
4. 提交版本升级并推送：

```bash
git add src/EasiAuto/__init__.py pyproject.toml uv.lock
git commit -m "upgrade: <新版本>"
git push
```

### 第二步：总结更新日志

找到上次发版的 git tag：

```bash
git tag --sort=-v:refname | head -1
```

获取从上个 tag 到 HEAD 的 commits：

```bash
git log <上个tag>..HEAD --oneline --no-merges
```

#### 为亮点功能查看代码

亮点功能需要**准确的用户感知描述**，仅凭 commit message 往往不够。对每个可能成为亮点的 `feat:` commit：

```bash
git show <commit_hash> --stat         # 先看改动范围和文件列表
git show <commit_hash> --no-stat      # 深入看具体 diff
```

重点关注：

- 新增的 UI 组件 / 页面 → 描述其用途和交互
- 新增的用户可操作功能 → 描述操作路径和效果
- 新的自动化能力 → 描述触发条件和结果
- 配置项变更 → 描述新增了什么可配置项

根据代码中的注释、UI 文本、日志消息来提炼功能描述，确保描述**精确实质**而非泛泛而谈。

#### 内容筛选规则

| 规则 | 说明 |
|------|------|
| 合并同类 | 多个 commit 实现同一功能 → 合为一条 |
| 忽略内部修复 | bug fix 修复的是本版本引入的问题（tag 之后的）→ 忽略 |
| 忽略技术性更改 | `refactor`、`style`、`chore`、`ci`、`docs` 一般不提及，除非改动幅度大（如"重构通知服务"） |
| 提取用户感知 | 从 `feat:`、`fix:`、`build:` 等前缀中提取用户可感知的变化 |

**识别同一功能的方法**：

- 多个 commit 的 `feat:` 描述指向同一功能模块（如"隐私保护遮罩"）
- 一个 commit 实现组件，另一个 commit 集成它 → 合并
- 若不确认是否应合并，倾向于分开列出，让用户审核时决定

#### 输出格式

直接输出 JSON，字段与发版工具 `update-manifest` 的 `--desc`、`--highlights`、`--others` 参数一一对应：

```json
{
  "desc": "<概括本版本的主要更改，或特别注意事项。非必填，可留空字符串。>",
  "highlights": [
    {"name": "<名称>", "description": "<一句话概括功能>"}
  ],
  "others": [
    "新增 <功能>",
    "优化 <改进>",
    "修复 <问题>"
  ]
}
```

- `others` 中每条以**类型前缀**开头：`新增` / `优化` / `修复` / `调整` / `移除`/ `重构` / `其他`
- `highlights` 为功能亮点，与 `others` 互不重复

**示例**：

```json
{
  "desc": "此版本引入了隐私保护、二维码登录等多项新功能，并修复了档案校验时机错误的问题。",
  "highlights": [
    {"name": "登录状态浮窗", "description": "一目了然地显示当前登录任务执行状态，同时支持打断登录"},
    {"name": "隐私保护遮罩", "description": "登录时自动覆盖桌面敏感信息，防止被录屏或投屏泄露"}
  ],
  "others": [
    "新增 远程公告",
    "新增 二维码登录",
    "优化 构建脚本与发版工具",
    "修复 档案校验时机错误"
  ]
}
```

此 JSON 可直接传入发版 CLI

### 第三步：推断元数据

基于版本号自动推断，除非用户明确指定。依据 [PEP 440](https://peps.python.org/pep-0440/) 版本排序规则：

```
.devN  <  aN  <  bN  <  rcN  <  (正式版)  <  .postN
```

**预发布（is_dev = true）**：排序在正式版之前，代表不稳定版本。

**正式版 / 发布后修订（is_dev = false）**：排序 ≥ 正式版，代表稳定版本。

| 段类型 | 规范拼写 | 别名 | EasiAuto 示例 | is_dev |
|--------|---------|------|-------------|--------|
| 开发版 | `.devN` | — | `1.2.0.dev1` | ✅ true |
| Alpha | `aN` | `alphaN` | `1.2.0a1` | ✅ true |
| Beta | `bN` | `betaN` | `1.2.0b1` | ✅ true |
| RC | `rcN` | `cN`, `preN`, `previewN` | `1.2.0rc1` | ✅ true |
| 正式版 | (无后缀) | — | `1.2.1` | ❌ false |
| 发布后修订 | `.postN` | `rN`, `revN` | `1.1.4r1` | ❌ false |

> **注意**：EasiAuto 项目使用的 `r1` 格式 (`1.1.4r1`) 是 post-release（发布后修订），**不是**预发布。它排序在 `1.1.4` 之后，属于稳定版本。

| 条件 | confirm_required |
|------|-----------------|
| 用户明确指示 | 按用户说的 |
| 存在破坏性更新（如移除功能、不兼容的 API 变更） | true |
| 其他情况 | false |

| 条件 | push_to_beta |
|------|-------------|
| is_dev = true | 不适用（置为 false） |
| 正式版，用户未指定 | false（让用户审核时决定） |

**推断完成后，明确告知用户每项元数据的值和推断依据。**

### 第四步：用户审核

将以下内容整理为清晰格式，提交用户审核：

1. 目标版本号
2. 元数据（is_dev、confirm_required、push_to_beta）
3. 完整的更新日志（说明 + 亮点 + 其他更新）

等待用户确认或修改后再继续。

### 第五步：发布

审核通过后，使用 `dist-center release` CLI 命令执行构建并发布 Release

```bash
uv run dist-center release \
  --version "<版本>" \
  --build-first \
  --build-full --build-lite \
  --desc "<说明>" \
  --highlights '<亮点JSON数组>' \
  --others '<其他JSON数组>'
```

## 版本号规范

遵循 [PEP 440](https://peps.python.org/pep-0440/)。EasiAuto 使用的段类型，按排序从低到高：

| 阶段 | 格式 | 示例 | is_dev |
|------|------|------|--------|
| 开发版 | `X.Y.Z.devN` | `1.2.0.dev1` | true |
| Alpha | `X.Y.ZaN` | `1.2.0a1` | true |
| Beta | `X.Y.ZbN` | `1.2.0b1` | true |
| RC | `X.Y.ZrcN` | `1.2.0rc1` | true |
| **正式版** | `X.Y.Z` | `1.2.1` | **false** |
| 发布后修订 | `X.Y.Z.postN` 或 `X.Y.ZrN` | `1.1.4r1` | false |

> `rN` 是 `postN` / `revN` 的别名，排序在正式版**之后**，属稳定版本。

## 参考

- 发行中心源码：`tools/distribution_center/`
- 主程序版本定义：`src/EasiAuto/__init__.py`
- 项目配置：`pyproject.toml`
