
# EasiAuto

![EasiAuto 宣传图](docs/EasiAutoPoster.PNG)

一个使用 Python 编写的 CLI 工具，可以用于自动登录希沃白板。通过 PyAutoGUI 实现自动识别并点击来模拟登录。

推荐与 [ClassIsland](https://github.com/ClassIsland/ClassIsland/) 的 **「自动化」** 功能结合使用，可实现在指定课程开始时自动登录至任课老师的希沃账号。具体自动化配置方案，详见 <https://forum.smart-teach.cn/d/725>

系统需求：Windows 10 及以上版本 | [下载](https://github.com/hxabcd/easiauto/releases/latest)

## ✨亮点

* **醒目的横幅警示**：兼具实用性与视觉冲击力

![醒目的横幅警告](docs/banner.webp)

* **单次跳过**：满足特殊场景下的灵活需求

![单次跳过](docs/skip_once.webp)

* **运行前显示警告弹窗**：让自动运行不再措不及防

![运行前警告](docs/warning.png)

* **自动错误重试**：无惧登录流程被打断

* **自动焦点切换**：解决因焦点丢失导致的登录打断

## 🪄 使用

使用已预先打包的可执行文件，直接通过命令行进行调用。

```pwsh
# 首次运行，创建配置文件
easiauto

# 查看使用说明
easiauto -h

# 运行自动登录
easiauto login -a ACCOUNT -p PASSWORD

# 跳过下一次登录
easiauto skip

```

## 🔧 配置

第一次运行程序时，会在程序所在目录下创建配置文件 `config.json`，随后程序自动退出。此时按照说明配置好自动登录选项，之后即可正常运行

可用的选项：

* `show_warning`: 是否在自动登录前弹出警告弹窗，默认禁用

* `timeout`: 警告弹窗的超时时长，值为正整数，默认为 15 秒

* `show_banner`: 是否在登录期间启用警示横幅，默认启用

* `4k_mode`: 启用 4K 兼容模式（可能存在部分适配不完全）

* `login_directly`: 跳过点击进入登录界面，适用于不进入白板界面的情况

* `skip_once`: 跳过下一次自动登录，随后自动重置

* `kill_seewo_agent`: 干掉 SeewoAgent，避免快捷登录导致冲突，默认启用

* `max_retries`: 错误重试次数，默认为 2

* `{easinote}`

  * `path`: 希沃白板程序路径，指向`swenlauncher.exe`，用于启动希沃白板。默认为 `auto`，即自动查找

  * `process_name`: 希沃白板进程名，用于终止进程。默认为 `EasiNote.exe`

  * `args`: 希沃白板启动参数，默认为空。设置为 `-m Display iwb` 时可以使非希沃设备跳过登录，直接进入白板界面

* `log_level`: 日志级别，选项有 `DEBUG` `INFO` `WARNING` `ERROR` `CRITICAL`，默认为 `WARNING`

## 开发

使用 **Python 3.13** 开发

使用 **uv** 管理项目环境

使用 **Nuitka** 构建
