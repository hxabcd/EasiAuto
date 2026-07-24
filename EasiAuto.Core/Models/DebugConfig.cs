using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 调试与开发选项
/// </summary>
public partial class DebugConfig : ObservableObject
{
    /// <summary>启用彩蛋</summary>
    [ObservableProperty]
    public partial bool IsEasterEggEnabled { get; set; } = false;

    /// <summary>启用开发选项</summary>
    [ObservableProperty]
    public partial bool IsDebugModeEnabled { get; set; } = false;

    /// <summary>启用诊断日志</summary>
    [ObservableProperty]
    public partial bool IsVerboseLogEnabled { get; set; } = false;

    /// <summary>使用备用窗口查找方法</summary>
    [ObservableProperty]
    public partial bool UseAlternateFindWindowMethod { get; set; } = false;
}
