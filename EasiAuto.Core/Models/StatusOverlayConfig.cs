using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 状态浮窗配置：登录时在屏幕中间下方显示当前登录任务执行状态
/// </summary>
public partial class StatusOverlayConfig : ObservableObject
{
    /// <summary>启用状态浮窗</summary>
    [ObservableProperty]
    public partial bool IsEnabled { get; set; } = true;
}
