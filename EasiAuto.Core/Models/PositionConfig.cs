using System.Drawing;
using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// FixedAutomator 使用的位置坐标（基于 1920×1080 100% 缩放）
/// </summary>
public partial class PositionConfig : ObservableObject
{
    /// <summary>
    /// 启用智能缩放：根据系统分辨率和缩放自动调整坐标。
    /// 若启用，设置的坐标必须基于 1920×1080 100% 缩放。
    /// </summary>
    [ObservableProperty]
    public partial bool IsScalingEnabled { get; set; } = true;

    /// <summary>进入登录界面按钮</summary>
    [ObservableProperty]
    public partial Point EnterLoginButton { get; set; } = new(172, 1044);

    /// <summary>切换到"账号登录"标签页的按钮</summary>
    [ObservableProperty]
    public partial Point AccountLoginTab { get; set; } = new(1090, 350);

    /// <summary>账号输入框</summary>
    [ObservableProperty]
    public partial Point AccountInput { get; set; } = new(1000, 420);

    /// <summary>密码输入框</summary>
    [ObservableProperty]
    public partial Point PasswordInput { get; set; } = new(1000, 490);

    /// <summary>同意协议复选框</summary>
    [ObservableProperty]
    public partial Point AgreementCheckbox { get; set; } = new(935, 724);

    /// <summary>登录按钮</summary>
    [ObservableProperty]
    public partial Point LoginButton { get; set; } = new(1090, 560);

    /// <summary>基准分辨率</summary>
    [ObservableProperty]
    public partial Size BaseSize { get; set; } = new(1920, 1080);

    /// <summary>登录界面窗口大小</summary>
    [ObservableProperty]
    public partial Size LoginWindowSize { get; set; } = new(808, 582);
}
