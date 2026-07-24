using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 警告弹窗配置：在运行自动登录前显示警告弹窗
/// </summary>
public partial class WarningConfig : ObservableObject
{
    /// <summary>启用警告弹窗</summary>
    [ObservableProperty]
    public partial bool IsEnabled { get; set; } = true;

    /// <summary>超时时长（秒）</summary>
    [ObservableProperty]
    public partial int Timeout { get; set; } = 60;

    /// <summary>最大推迟次数</summary>
    [ObservableProperty]
    public partial int MaxDelays { get; set; } = 1;

    /// <summary>推迟时长（秒）</summary>
    [ObservableProperty]
    public partial int DelayTime { get; set; } = 150;

    /// <summary>在警告弹窗中显示目标登录账号的用户名</summary>
    [ObservableProperty]
    public partial bool IsUserNameVisible { get; set; } = true;
}
