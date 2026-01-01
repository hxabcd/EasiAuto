
# EasiAuto

![EasiAuto 宣传图](docs/EasiAutoPoster.png)

EasiAuto 是一款自动登录希沃白板的小工具，可以通过一行命令快速登录进入希沃白板。

推荐与 [ClassIsland](https://github.com/ClassIsland/ClassIsland/) 的 **「自动化」** 功能结合使用，可实现在指定课程开始时自动登录至任课老师的希沃账号。具体自动化配置方案，详见 <https://forum.smart-teach.cn/d/725>

系统需求：Windows 10 及以上版本 | [下载](https://github.com/hxabcd/EasiAuto/releases/latest)

## ✨亮点

* **完备的识别方式**：具有 UIA 自动定位、OpenCV 图像识别定位、~~固定位置（未完成）~~ 三种登录方案，可根据需求切换

* **运行前显示警告弹窗**：让自动运行不再措不及防

![运行前警告](docs/warning.png)

* **醒目的横幅警示**：兼具实用性与视觉冲击力，同时支持高度自定义

![醒目的横幅警告](docs/banner.webp)

* **单次跳过**：暂时禁用自动登录，满足特殊场景下的灵活需求

* **错误重试**：无惧登录流程被打断

## 🪄 使用

双击 `EasiAuto.exe`，打开设置界面进行配置。

配置完毕后，通过命令行进行调用

```pwsh
# 运行自动登录
.\EasiAuto.exe login -a ACCOUNT -p PASSWORD

# 跳过下一次登录
.\EasiAuto.exe skip

# 查看使用说明
.\EasiAuto.exe -h
```

## 自动化

见 <https://forum.smart-teach.cn/d/725>

> [!NOTE]  
> 即将发布的 1.1 版本将加入 ClassIsland 配置自动生成，可直接将自动化写入 ClassIsland 配置文件，敬请期待

## 开发

使用 **Python 3.13** 开发

使用 **uv** 管理项目环境

使用 **Nuitka** 构建
