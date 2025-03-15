
# Auto Login for EasiNote

## 概述

一个使用 Python 编写的 CLI 工具，可以用于自动登录希沃白板。通过 PyAutoGUI 实现自动识别并点击来模拟登录。

推荐与 [ClassIsland](https://github.com/ClassIsland/ClassIsland/) 的 **「自动化」** 功能结合使用，可实现在指定课程开始时自动登录至任课老师的希沃账号。

系统需求：Windows 10 及以上版本

目前已在本人班级内的 Windows 10 希沃一体机上进行了一段时间的测试，基本没有问题。偶尔可能会因为同学或老师误触导致登录被打断，此时会进行错误重试

## 使用

使用已预先打包的可执行文件，直接通过命令行进行调用。

```pwsh
# 查看使用说明
auto_login_for_easinote.exe -h
```

### 指定账号密码

* 通过 `-a` 或 `--account` 参数指定账号

* 通过 `-p` 或 `--password` 参数指定密码

```pwsh
auto_login_for_easinote.exe -a {手机号} -p {密码}
```

### 显示警告

通过 `-w` 或 `--show-warning` 参数显示警告

```pwsh
auto_login_for_easinote.exe -a {手机号} -p {密码} -w
```

启用后，将会在自动登录前通过 Windows 的系统通知进行提示，超时时长 15 秒。

如超时或选择忽略，则继续登录；如选择取消，则结束程序。

此功能目的是为了避免某些不需要自动登录的特殊情况下希沃白板被强行退出，影响正常授课。

### 启用 4K 适配

通过 `--4k` 参数启用 4K 分辨率适配

```pwsh
auto_login_for_easinote.exe -a {手机号} -p {密码} --4k
```

### 显示日志输出

通过 `--debug` 参数显示日志输出

```pwsh
auto_login_for_easinote.exe -a {手机号} -p {密码} --debug
```
