"""设计令牌：集中管理项目中的颜色、圆角等设计决策

所有自定义组件统一引用这里，避免散落的硬编码值。
颜色统一为 HEX 字符串，带透明度时使用 ``#AARRGGBB`` 格式；
亮色/暗色主题以 ``_LIGHT`` / ``_DARK`` 后缀区分。
"""

# ========== 品牌色 ==========
BRAND = "#00C884"  # EasiAuto 主题绿（qfluentwidgets themeColor、主标签、选中边框等）

# ========== 文本色 ==========
TEXT_SECONDARY_LIGHT = "#878787"  # 次要文本（亮色主题）
TEXT_SECONDARY_DARK = "#B5B5B5"  # 次要文本（暗色主题）
TEXT_MUTED = "#555555"  # 弱化文本（隐私遮罩）

# ========== 状态浮窗 ==========
OVERLAY_TEXT = "#FFFFFF"
OVERLAY_TEXT_DIM = "#CDCDCD"
OVERLAY_CARD_BG = "#99000000"  # 卡片背景（60% 黑）
OVERLAY_BOTTOM_BG = "#D9464646"  # 底部操作条背景（85% 灰）
OVERLAY_SHADOW = "#40000000"  # 阴影

# ========== 标签 ==========
TAG_NEUTRAL_BG = "#339E9E9E"
TAG_NEUTRAL_TEXT_LIGHT = "#424242"
TAG_NEUTRAL_TEXT_DARK = "#E0E0E0"
TAG_NEUTRAL_BORDER_LIGHT = "#9E9E9E"
TAG_NEUTRAL_BORDER_DARK = "#757575"
TAG_BRAND_BG = "#3300C884"
TAG_BRAND_TEXT_LIGHT = "#275317"
TAG_BRAND_TEXT_DARK = "#CDFFE4"

# ========== 严重性（公告卡片） ==========
SEVERITY_WARNING_BG_LIGHT = "#FFF4CE"
SEVERITY_WARNING_BG_DARK = "#5C4500"
SEVERITY_ERROR_BG_LIGHT = "#FDE7E9"
SEVERITY_ERROR_BG_DARK = "#442726"
SEVERITY_WARNING_ACCENT = "#FFB900"
SEVERITY_ERROR_ACCENT = "#A4262C"

# ========== 绑定页边框 / 分隔线 ==========
SELECTED_BORDER = "#D900C884"  # 选中卡片（主题绿 85%）
UNSELECTED_BORDER = "#00787878"
DIVIDER = "#50787878"
DIVIDER_TEXT = "#B4787878"

# ========== 圆角 ==========
RADIUS_SETTING = 6  # 设置卡片（SettingCard、公告卡片）
RADIUS_CARD = 8  # 绑定页卡片
RADIUS_OVERLAY = 12  # 状态浮窗卡片
RADIUS_TAG = 4  # 标签

# ========== 布局 ==========
MAX_CONTENT_WIDTH = 900  # 页面内容（卡片）最大宽度
