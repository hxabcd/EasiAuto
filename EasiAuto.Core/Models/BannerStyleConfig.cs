using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 警示横幅样式配置
/// 
/// </summary>
public partial class BannerStyleConfig : ObservableObject
{
    /// <summary>横幅中滚动的文本内容</summary>
    [ObservableProperty]
    public partial string Text { get; set; } = "  ⚠️WARNING⚠️  正在运行希沃白板自动登录  请勿触摸一体机";

    /// <summary>横幅文本使用的字体名称</summary>
    [ObservableProperty]
    public partial string TextFont { get; set; } = "HarmonyOS Sans SC";

    /// <summary>横幅文本的颜色</summary>
    [ObservableProperty]
    public partial string TextColor { get; set; } = "#FFFFDE59";

    /// <summary>横幅高亮或装饰元素的颜色</summary>
    [ObservableProperty]
    public partial string FgColor { get; set; } = "#C8FFDE59";

    /// <summary>横幅的背景色</summary>
    [ObservableProperty]
    public partial string BgColor { get; set; } = "#B4E4080A";

    /// <summary>横幅的每秒更新次数</summary>
    [ObservableProperty]
    public partial int Fps { get; set; } = 60;

    /// <summary>横幅文本每次刷新滚动的距离</summary>
    [ObservableProperty]
    public partial int TextSpeed { get; set; } = 3;

    /// <summary>横幅距离屏幕顶部的像素偏移量</summary>
    [ObservableProperty]
    public partial int YOffset { get; set; } = 20;
}
