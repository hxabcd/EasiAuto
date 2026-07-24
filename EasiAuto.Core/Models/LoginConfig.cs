using CommunityToolkit.Mvvm.ComponentModel;
using EasiAuto.Core.Enums;

namespace EasiAuto.Core.Models;

/// <summary>
/// 登录相关配置（聚合 EasiNote、Timeout、Position 子模型）
/// </summary>
public partial class LoginConfig : ObservableObject
{
    /// <summary>登录方式</summary>
    [ObservableProperty]
    public partial LoginMethod Method { get; set; } = LoginMethod.Fixed;

    /// <summary>下次运行时跳过自动登录</summary>
    [ObservableProperty]
    public partial bool IsSkipOnceEnabled { get; set; } = false;

    /// <summary>若已登录同一账号则跳过</summary>
    [ObservableProperty]
    public partial bool ShouldSkipIfLoggedIn { get; set; } = true;

    /// <summary>终止 EasiAgent 服务</summary>
    [ObservableProperty]
    public partial bool ShouldKillAgent { get; set; } = false;

    /// <summary>需要进入登录界面（适用于 iwb 场景）</summary>
    [ObservableProperty]
    public partial bool IsIwb { get; set; } = true;

    /// <summary>强制启用兼容模式输入</summary>
    [ObservableProperty]
    public partial bool ForceCompatibilityMode { get; set; } = false;

    /// <summary>隐私保护遮罩</summary>
    [ObservableProperty]
    public partial PrivacyMaskConfig PrivacyMask { get; set; } = new();


    /// <summary>希沃白板选项</summary>
    [ObservableProperty]
    public partial EasiNoteConfig EasiNote { get; set; } = new();

    /// <summary>等待时长</summary>
    [ObservableProperty]
    public partial TimeoutConfig Timeout { get; set; } = new();

    /// <summary>位置坐标</summary>
    [ObservableProperty]
    public partial PositionConfig Position { get; set; } = new();
}