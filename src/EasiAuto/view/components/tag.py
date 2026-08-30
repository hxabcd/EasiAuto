from qfluentwidgets import (
    FluentLabelBase,
    FluentStyleSheet,
    getFont,
    setCustomStyleSheet,
)

from EasiAuto.view.tokens import (
    BRAND,
    RADIUS_TAG,
    TAG_BRAND_BG,
    TAG_BRAND_TEXT_DARK,
    TAG_BRAND_TEXT_LIGHT,
    TAG_NEUTRAL_BG,
    TAG_NEUTRAL_BORDER_DARK,
    TAG_NEUTRAL_BORDER_LIGHT,
    TAG_NEUTRAL_TEXT_DARK,
    TAG_NEUTRAL_TEXT_LIGHT,
)


class TagLabel(FluentLabelBase):
    """标签组件"""

    lightQss = (
        "FluentLabelBase{"
        f"background-color: {TAG_NEUTRAL_BG}; color: {TAG_NEUTRAL_TEXT_LIGHT}; font-size: 12px;"
        f"border: 1px solid {TAG_NEUTRAL_BORDER_LIGHT}; border-radius: {RADIUS_TAG}px;"
        "}"
    )
    darkQss = (
        "FluentLabelBase{"
        f"background-color: {TAG_NEUTRAL_BG}; color: {TAG_NEUTRAL_TEXT_DARK}; font-size: 12px;"
        f"border: 1px solid {TAG_NEUTRAL_BORDER_DARK}; border-radius: {RADIUS_TAG}px;"
        "}"
    )

    def getFont(self):
        return getFont(12)

    def _init(self):
        FluentStyleSheet.LABEL.apply(self)
        self.setFont(self.getFont())
        self.setTextColor()
        # qconfig.themeChanged.connect(lambda: self.setTextColor(self.lightColor, self.darkColor))

        self.customContextMenuRequested.connect(self._onContextMenuRequested)
        setCustomStyleSheet(self, lightQss=self.lightQss, darkQss=self.darkQss)

        return self


class PrimaryTagLabel(TagLabel):
    """带主题色的标签组件（使用 EasiAuto 品牌主题色）"""

    lightQss = (
        "FluentLabelBase{"
        f"background-color: {TAG_BRAND_BG}; color: {TAG_BRAND_TEXT_LIGHT}; font-size: 12px;"
        f"border: 1px solid {BRAND}; border-radius: {RADIUS_TAG}px;"
        "}"
    )
    darkQss = (
        "FluentLabelBase{"
        f"background-color: {TAG_BRAND_BG}; color: {TAG_BRAND_TEXT_DARK}; font-size: 12px;"
        f"border: 1px solid {BRAND}; border-radius: {RADIUS_TAG}px;"
        "}"
    )
