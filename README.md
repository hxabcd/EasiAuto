<div align="center">

![EasiAuto 宣传图](docs/EasiAutoPoster.png)

一款自动登录希沃白板的小工具，通过模拟登录流程来实现自动登录。

[![最新版本](https://img.shields.io/github/v/release/hxabcd/EasiAuto?style=for-the-badge&color=00b4ab&label=最新正式版)](https://github.com/hxabcd/EasiAuto/releases/latest)
[![上次更新](https://img.shields.io/github/last-commit/hxabcd/EasiAuto?style=for-the-badge&color=00b4ab&label=最后更新时间)](https://github.com/hxabcd/EasiAuto/commits/master)
[![下载统计](https://img.shields.io/github/downloads/hxabcd/EasiAuto/total?style=for-the-badge&color=00b4ab&label=累计下载)](https://github.com/hxabcd/EasiAuto/releases)

[![QQ群](https://img.shields.io/badge/-QQ%E7%BE%A4%EF%BD%9C821944413%20%28BSOD%E2%80%94MEMZ%29-blue?style=for-the-badge&logo=QQ)](https://qm.qq.com/q/5TV3Pvb2M2)
[![bilibili](https://img.shields.io/badge/-哔哩哔哩-%23FB7299?style=for-the-badge&logo=bilibili)](https://space.bilibili.com/401002238)

![Python](https://img.shields.io/badge/基于Python%203.13-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![uv](https://img.shields.io/badge/使用uv管理-%23DE5FE9.svg?style=for-the-badge&logo=uv&logoColor=white)
![PySide6](https://img.shields.io/badge/PySide6-%23217346.svg?style=for-the-badge&logo=Qt&logoColor=white)
![Sentry](https://img.shields.io/badge/已接入sentry-%23362D59.svg?style=for-the-badge&logo=sentry&logoColor=white)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge)](https://opensource.org/licenses/GPL-3.0)

</div>

![醒目的警示横幅](docs/ui/banner.png)

> [!NOTE]
> 推荐同时安装 [ClassIsland](https://github.com/ClassIsland/ClassIsland/)，在指定课程开始时自动执行登录任务，实现全自动登录的智慧教学新体验。
> 
> 可在软件的「自动化」界面中快速配置 ClassIsland 自动化。


> [!NOTE]
> 系统需求：Windows 10 及以上版本 | [下载](https://github.com/hxabcd/EasiAuto/releases/latest)

## ✨亮点

* **易用的设置界面**：前所未有的 ClassIsland 自动化编辑体验，简单几步即可配置完成
* **完备的登录方式**：具有 固定位置、图像识别、自动定位、进程注入 四种登录方案，根据需求灵活切换
* **运行前显示警告弹窗**：自动运行不再措不及防，还可暂时推迟登录
* **醒目的横幅警示**：兼具实用性与视觉冲击力，同时支持高度自定义
* **单次跳过**：暂时禁用自动登录，满足特殊场景下的灵活需求
* **错误重试**：无惧登录流程被打断
* **自动更新**：及时接收功能增强和问题修复

## 🖼️ 截图

<details>
<summary> 📸 点击这里展开 📸 </summary>

<div align="center">

<img src="docs/ui/banner.png" alt="警示横幅"> <br> 警示横幅

<img src="docs/ui/warning.png" alt="运行前警告"> <br> 运行前警告弹窗

<img src="docs/ui/setting.png" alt="设置页" height="400px"> <br> 设置页

<img src="docs/ui/ciautoedit.png" alt="自动化页" height="400px"> <br> 自动化页

<img src="docs/ui/update.png" alt="更新页" height="400px"> <br> 更新页

</div>

</details>

## 🪄 使用

下载后，将程序解压缩到你指定的文件夹，随后双击 `EasiAuto.exe` 启动程序。

在设置界面中可更改配置项，在自动化页添加档案到 ClassIsland，同时也可以创建快捷方式到桌面。

此外，通过命令行进行调用的方法如下：

```pwsh
# 运行自动登录
.\EasiAuto.exe login -a ACCOUNT -p PASSWORD

# 跳过下一次登录
.\EasiAuto.exe skip

# 查看完整使用说明
.\EasiAuto.exe -h
```
