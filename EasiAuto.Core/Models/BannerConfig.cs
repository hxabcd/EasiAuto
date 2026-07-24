using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 警示横幅配置：运行自动登录时在屏幕顶部显示醒目的警示横幅
/// </summary>
public partial class BannerConfig : ObservableObject
{
    /// <summary>启用警示横幅</summary>
    [ObservableProperty]
    public partial bool IsEnabled { get; set; } = true;

    /// <summary>横幅样式</summary>
    [ObservableProperty]
    public partial BannerStyleConfig Style { get; set; } = new();
}
