from loguru import logger

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScroller,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    AvatarWidget,
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ExpandGroupSettingCard,
    FluentIcon,
    HyperlinkCard,
    ImageLabel,
    SmoothScrollArea,
    SubtitleLabel,
    TitleLabel,
)

from EasiAuto import __version__
from EasiAuto.common.consts import IS_FULL
from EasiAuto.common.utils import get_resource


class AboutPage(SmoothScrollArea):
    """设置 - 关于页"""

    def __init__(self):
        super().__init__()
        logger.debug("初始化关于页")
        self.setObjectName("AboutPage")
        self.setStyleSheet("border: none; background-color: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = TitleLabel("关于")
        title.setContentsMargins(36, 8, 0, 12)
        layout.addWidget(title)

        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        QScroller.grabGesture(self.scroll_area.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)
        layout.addWidget(self.scroll_area)

        # 居中容器
        self.scroll_container = QWidget()
        self.scroll_area.setWidget(self.scroll_container)

        self.scroll_container_layout = QHBoxLayout(self.scroll_container)
        self.scroll_container_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_container_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.content_widget = QWidget()
        self.content_widget.setMaximumWidth(600)
        self.scroll_container_layout.addWidget(self.content_widget)

        # 内容容器
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 20)
        self.content_layout.setSpacing(28)

        # 产品信息卡片
        self.banner_container = CardWidget()
        banner_container_layout = QVBoxLayout(self.banner_container)
        banner_container_layout.setContentsMargins(0, 0, 0, 0)
        banner_container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 主视觉图
        _banner_img_src = QPixmap(get_resource("banner.png"))
        banner_image = ImageLabel(_banner_img_src)
        banner_image.setFixedWidth(600)
        banner_image.scaledToWidth(600)
        banner_image.setBorderRadius(8, 8, 0, 0)
        banner_container_layout.addWidget(banner_image)

        banner_layout = QVBoxLayout()
        banner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        banner_layout.setContentsMargins(20, 0, 20, 12)
        banner_layout.setSpacing(16)

        # 应用描述
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        title = TitleLabel("EasiAuto", self)
        subtitle = SubtitleLabel(f"版本 v{__version__} ({'FULL' if IS_FULL else 'LITE'})", self)
        title_layout.addWidget(title)
        title_layout.addSpacing(6)
        title_layout.addWidget(subtitle)
        title_layout.addStretch(1)

        banner_layout.addLayout(title_layout)

        description_layout = QVBoxLayout()
        product_text = BodyLabel("一款自动登录希沃白板的小工具")
        github_link = HyperlinkCard(
            icon=FluentIcon.GITHUB,
            title="GitHub 仓库",
            content="不妨点个 Star 支持一下？  (≧∇≦)ﾉ★",
            url="https://github.com/hxabcd/EasiAuto",
            text="查看",
        )
        additional_info = ExpandGroupSettingCard(
            icon=FluentIcon.INFO, title="其他信息", content="开源协议、第三方库、鸣谢"
        )
        additional_info.viewLayout.setContentsMargins(16, 8, 16, 12)
        additional_info.viewLayout.setSpacing(6)
        additional_info.addGroupWidget(BodyLabel("本项自基于 GNU General Public License v3.0 (GPLv3) 获得许可"))
        additional_info.addGroupWidget(
            BodyLabel(
                "\n  - ".join(
                    [
                        "本项目使用到的第三方库及项目（仅列出部分）：",
                        "qfluentwidget",
                        "PySide6",
                        "Pydantic",
                        "pywinauto",
                        "pyautogui",
                        "opencv-python",
                        "Snoop",
                        "loguru",
                        "sentry-sdk",
                        "windows11toast",
                    ]
                )
            )
        )
        additional_info.addGroupWidget(
            BodyLabel(
                "\n  - ".join(
                    [
                        "特别感谢：",
                        "智教联盟 对本项目的宣传",
                        "Class-Widget 对本项目代码提供参考",
                        "ClassIsland 「自动化」 对本项目提供载体",
                        "我的初中英语老师 为本项目提供动机",
                    ]
                )
                + "\n\n    以及——愿意使用 EasiAuto 的你"
            )
        )
        description_layout.addWidget(product_text)
        description_layout.addWidget(github_link)
        description_layout.addWidget(additional_info)  # NOTE: 不知道为什么折叠的时候会抽搐，之后再修吧
        banner_layout.addLayout(description_layout)

        banner_container_layout.addLayout(banner_layout)
        self.content_layout.addWidget(self.banner_container)

        # 作者信息卡片
        self.author_area = CardWidget()
        author_layout = QVBoxLayout(self.author_area)
        author_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        author_layout.setContentsMargins(24, 16, 24, 16)

        author_info_layout = QHBoxLayout()

        author_avatar = AvatarWidget(QPixmap(get_resource("author_avatar.jpg")))
        author_avatar.setRadius(24)

        sub_layout = QVBoxLayout()
        sub_layout.setSpacing(0)
        author_name = SubtitleLabel("HxAbCd")
        author_content = CaptionLabel("Just be yourself.  >_<")
        author_content.setTextColor(QColor("#878787"), QColor("#b5b5b5"))
        sub_layout.addWidget(author_name)
        sub_layout.addWidget(author_content)

        author_info_layout.addWidget(author_avatar)
        author_info_layout.addSpacing(4)
        author_info_layout.addLayout(sub_layout)
        author_info_layout.addStretch(1)

        author_link1 = HyperlinkCard(
            icon=FluentIcon.GLOBE,
            title="个人网站",
            url="https://0xabcd.dev",
            text="访问",
        )
        author_link2 = HyperlinkCard(
            icon=FluentIcon.HOME_FILL,
            title="哔哩哔哩主页",
            url="https://space.bilibili.com/401002238",
            text="访问",
        )
        author_link3 = HyperlinkCard(
            icon=FluentIcon.GITHUB,
            title="Github 主页",
            url="https://github.com/hxabcd",
            text="访问",
        )

        author_layout.addLayout(author_info_layout)
        author_layout.addSpacing(4)
        author_layout.addWidget(author_link1)
        author_layout.addWidget(author_link2)
        author_layout.addWidget(author_link3)

        self.content_layout.addWidget(self.author_area)
        self.content_layout.addStretch(1)
