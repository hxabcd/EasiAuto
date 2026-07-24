using System.ComponentModel;

namespace EasiAuto.Core.Enums;

/// <summary>
/// 更新通道
/// </summary>
public enum UpdateChannel
{
    [Description("稳定通道")] Release = 0,
    [Description("测试通道")] Dev = 1,
}