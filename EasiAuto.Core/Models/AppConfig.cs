using CommunityToolkit.Mvvm.ComponentModel;
using EasiAuto.Core.Enums;

namespace EasiAuto.Core.Models;

/// <summary>
/// 应用根配置，聚合所有子配置模块。
/// </summary>
public partial class AppConfig : ObservableObject
{
    /// <summary>应用主题</summary>
    [ObservableProperty]
    public partial ThemeOptions Theme { get; set; } = ThemeOptions.Auto;

    /// <summary>启用日志记录</summary>
    [ObservableProperty]
    public partial bool IsLogEnabled { get; set; } = true;

    /// <summary>启用遥测</summary>
    [ObservableProperty]
    public partial bool IsTelemetryEnabled { get; set; } = true;

    [ObservableProperty] public partial bool IsAutomationPageNotificationShown { get; set; } = false;


    /// <summary>登录选项</summary>
    [ObservableProperty]
    public partial LoginConfig Login { get; set; } = new();

    /// <summary>警告弹窗</summary>
    [ObservableProperty]
    public partial WarningConfig Warning { get; set; } = new();

    /// <summary>警示横幅</summary>
    [ObservableProperty]
    public partial BannerConfig Banner { get; set; } = new();

    /// <summary>状态浮窗</summary>
    [ObservableProperty]
    public partial StatusOverlayConfig StatusOverlay { get; set; } = new();

    /// <summary>ClassIsland 设置</summary>
    [ObservableProperty]
    public partial ClassIslandConfig ClassIsland { get; set; } = new();

    /// <summary>更新设置</summary>
    [ObservableProperty]
    public partial UpdateConfig Update { get; set; } = new();

    /// <summary>调试选项</summary>
    [ObservableProperty]
    public partial DebugConfig Debug { get; set; } = new();

    /// <summary>统计数据</summary>
    [ObservableProperty]
    public partial StatisticsConfig Statistics { get; set; } = new();

    /// <summary>公告设置</summary>
    [ObservableProperty]
    public partial AnnouncementConfig Announcement { get; set; } = new();
}