from qfluentwidgets import (
    FluentLabelBase,
    FluentStyleSheet,
    getFont,
    setCustomStyleSheet,
)


class TagLabel(FluentLabelBase):
    """标签组件"""

    lightQss = (
        "FluentLabelBase{"
        "background-color: #339E9E9E; color: #424242; font-size: 12px;"
        "border: 1px solid #9E9E9E; border-radius: 4px;"
        "}"
    )
    darkQss = (
        "FluentLabelBase{"
        "background-color: #339E9E9E; color: #E0E0E0; font-size: 12px;"
        "border: 1px solid #757575; border-radius: 4px;"
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
    """带主题色的标签组件（硬编码 EasiAuto 主题色）"""

    lightQss = (
        "FluentLabelBase{"
        "background-color: #3300C884; color: #275317; font-size: 12px;"
        "border: 1px solid #00C884; border-radius: 4px;"
        "}"
    )
    darkQss = (
        "FluentLabelBase{"
        "background-color: #3300C884; color: #CDFFE4; font-size: 12px;"
        "border: 1px solid #00C884; border-radius: 4px;"
        "}"
    )
