using CommunityToolkit.Mvvm.ComponentModel;

namespace EasiAuto.Core.Models;

/// <summary>
/// BaseAutomator 使用的等待时长配置（单位：秒）
/// </summary>
public partial class TimeoutConfig : ObservableObject
{
    /// <summary>终止进程后，等待其彻底结束的时间</summary>
    [ObservableProperty]
    public partial double Terminate { get; set; } = 1;

    /// <summary>启动后，等待其启动完成的最大时间</summary>
    [ObservableProperty]
    public partial double LaunchPollingTimeout { get; set; } = 30;

    /// <summary>轮询检测是否启动完成的时间间隔</summary>
    [ObservableProperty]
    public partial double LaunchPollingInterval { get; set; } = 0.5;

    /// <summary>启动后，等待界面加载的时间</summary>
    [ObservableProperty]
    public partial double AfterLaunch { get; set; } = 2;

    /// <summary>点击"登录"按钮后，等待界面出现的时间</summary>
    [ObservableProperty]
    public partial double EnterLoginUi { get; set; } = 3;

    /// <summary>等待切换到账号登录标签页的时间</summary>
    [ObservableProperty]
    public partial double SwitchTab { get; set; } = 1;
}