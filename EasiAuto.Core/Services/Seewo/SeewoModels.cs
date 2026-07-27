using System.Text.Json;

namespace EasiAuto.Core.Services.Seewo;

// ── 数据模型 ──────────────────────────────────────────

/// <summary>登录响应中的 user 字段</summary>
public class SeewoUserInfo
{
    public string Uid { get; init; } = "";
    public string Username { get; init; } = "";
    public string NickName { get; init; } = "";
    public string Phone { get; init; } = "";
    public string Email { get; init; } = "";
    public string PhotoUrl { get; init; } = "";
    public string AccountId { get; init; } = "";
    public string RealName { get; init; } = "";
    public string UnitId { get; init; } = "";
    public int AccountType { get; init; }
    public int Gender { get; init; }
    public string WechatUid { get; init; } = "";
    public string DingdingUid { get; init; } = "";
    public string AppCode { get; init; } = "";
    public string Address { get; init; } = "";
    public int IsRegister { get; init; }

    internal static SeewoUserInfo FromJson(JsonElement data)
    {
        var user = data.TryGetProperty("user", out var u) ? u : data;

        static string S(JsonElement e, string key)
        {
            if (e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String) return v.GetString()!;
            return "";
        }

        static int I(JsonElement e, string key) =>
            e.TryGetProperty(key, out var v) && v.TryGetInt32(out var n) ? n : 0;

        return new SeewoUserInfo
        {
            Uid = S(user, "uid"),
            Username = S(user, "username"),
            NickName = S(user, "nickName"),
            Phone = S(user, "phone"),
            Email = S(user, "email"),
            PhotoUrl = S(user, "photoUrl"),
            AccountId = S(user, "accountId"),
            RealName = S(user, "realName"),
            UnitId = S(user, "unitId"),
            AccountType = I(user, "accountType"),
            Gender = I(user, "gender"),
            WechatUid = S(user, "wechatUid"),
            DingdingUid = S(user, "dingdingUid"),
            AppCode = S(user, "appCode"),
            Address = S(user, "address"),
            IsRegister = I(data, "isRegister"),
        };
    }
}

/// <summary>登录成功时的完整结果</summary>
public class SeewoLoginResult
{
    public string Token { get; init; } = "";
    public SeewoUserInfo User { get; init; } = new();
    public int IsRegister { get; init; }
    /// <summary>原始 API 响应 JSON，便于调试</summary>
    public string? RawResponse { get; init; }

    internal static SeewoLoginResult FromJson(JsonElement response, string? raw = null)
    {
        var inner = response.TryGetProperty("data", out var d) ? d : response;

        return new SeewoLoginResult
        {
            Token = inner.TryGetProperty("token", out var t) ? t.GetString()! : "",
            User = SeewoUserInfo.FromJson(inner),
            IsRegister = inner.TryGetProperty("isRegister", out var r) && r.TryGetInt32(out var n) ? n : 0,
            RawResponse = raw,
        };
    }
}

/// <summary>GET /api/v2/user/info 返回的用户详情</summary>
public class SeewoUserProfile
{
    public string PhotoUrl { get; init; } = "";
    /// <summary>userInfoExtendVo.picUrl — 高清头像，通常比 photoUrl 尺寸更大</summary>
    public string PicUrl { get; init; } = "";
    public string Phone { get; init; } = "";
    public string Email { get; init; } = "";
    public string NickName { get; init; } = "";
    public string RealName { get; init; } = "";

    /// <summary>头像 URL，优先 picUrl > photoUrl</summary>
    public string? Avatar =>
        (!string.IsNullOrEmpty(PicUrl) ? PicUrl : null) ??
        (!string.IsNullOrEmpty(PhotoUrl) ? PhotoUrl : null);

    internal static SeewoUserProfile FromJson(JsonElement data)
    {
        var userData = data.TryGetProperty("data", out var d) ? d : data;
        var ext = userData.TryGetProperty("userInfoExtendVo", out var e) ? e : default(JsonElement?);

        static string S(JsonElement e, string key) =>
            e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";

        return new SeewoUserProfile
        {
            PhotoUrl = S(userData, "photoUrl"),
            PicUrl = ext.HasValue ? S(ext.Value, "picUrl") : "",
            Phone = S(userData, "phone"),
            Email = S(userData, "email"),
            NickName = S(userData, "nickName"),
            RealName = S(userData, "realName"),
        };
    }
}
