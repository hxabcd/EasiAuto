DEFAULT_CONFIG = """# auto_login_for_easinote 配置文件

# 是否在自动登录前通过系统通知弹出警告
# 默认超时时长为 15 秒
show_warning = false

# 是否启用 4K 兼容模式
4k_mode = false

# 是否直接登录，跳过点击进入登录界面
# 适用于打开希沃后不进入全屏黑板界面的情况
login_directly = false

# 配置日志级别
# 可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
# 默认为 WARNING
log_level = "WARNING"

[easinote]

# 希沃白板的程序路径，一般设置为swenlauncher.exe的路径
# 用于启动希沃白板
# 如果设置为 auto，则会自动查找
path = "auto"

# 希沃白板的进程名，一般为EasiNote.exe
# 用于终止希沃白板进程
process_name = "EasiNote.exe"

# 启动希沃白板的命令行参数，一般留空
# 如果需要跳过登录界面全屏启动，可以设置为"-m Display iwb"
args = ""
"""
