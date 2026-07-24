using System.Drawing;
using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// 隐私保护遮罩配置：登录时在输入框上显示遮罩，遮挡可能的隐私信息
/// </summary>
public partial class PrivacyMaskConfig : ObservableObject
{
    /// <summary>启用隐私保护遮罩</summary>
    [ObservableProperty]
    public partial bool IsEnabled { get; set; } = true;

    /// <summary>遮罩左上角坐标</summary>
    [ObservableProperty]
    public partial Point MaskLeftTop { get; set; } = new(868, 381);

    /// <summary>遮罩大小</summary>
    [ObservableProperty]
    public partial Size MaskSize { get; set; } = new(440, 386);
}
