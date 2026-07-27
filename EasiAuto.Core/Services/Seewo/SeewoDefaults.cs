using System.Security.Cryptography;
using System.Text;

namespace EasiAuto.Core.Services.Seewo;

// ═══════════════════════════════════════════════════════════
// 希沃白板 (EasiNote) 登录 API 常量与工具
// 基于 dnSpy 反编译 5.2.4.9440
// ═══════════════════════════════════════════════════════════

public static class SeewoDefaults
{
    public const string BaseUrl = "https://edu.seewo.com";
    public const string AppCode = "EasiNote5";
    public const string AppBrand = "";
    public const string LoginEndpoint = "/api/v1/auth/login";
    public const string UserInfoEndpoint = "/api/v2/user/info";
    public const string UserAgent = "EasiNote/5.2.4";
    public static readonly TimeSpan Timeout = TimeSpan.FromSeconds(30);
}

public static class SeewoCrypto
{
    /// <summary>MD5 哈希密码</summary>
    public static string HashPassword(string plain)
    {
        var hash = MD5.HashData(Encoding.UTF8.GetBytes(plain));
        return string.Concat(hash.Select(b => b.ToString("x2")));
    }
}
