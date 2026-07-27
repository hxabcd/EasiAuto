using System.Net.Http.Json;
using System.Text.Json;

namespace EasiAuto.Core.Services.Seewo;

// ── 客户端 ──────────────────────────────────────────

public class SeewoClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly bool _ownsHttpClient;
    private readonly string _baseUrl;
    private readonly string _appCode;
    private readonly string _appBrand;

    public SeewoClient(
        string baseUrl = SeewoDefaults.BaseUrl,
        string appCode = SeewoDefaults.AppCode,
        string appBrand = SeewoDefaults.AppBrand,
        TimeSpan? timeout = null,
        HttpClient? httpClient = null)
    {
        _baseUrl = baseUrl.TrimEnd('/');
        _appCode = appCode;
        _appBrand = appBrand;
        _ownsHttpClient = httpClient is null;
        _http = httpClient ?? new HttpClient();
        _http.Timeout = timeout ?? SeewoDefaults.Timeout;
        _http.DefaultRequestHeaders.TryAddWithoutValidation("User-Agent", SeewoDefaults.UserAgent);
        _http.DefaultRequestHeaders.TryAddWithoutValidation("Accept", "application/json");
    }

    public void Dispose()
    {
        if (_ownsHttpClient) _http.Dispose();
    }

    private string BuildCookie()
    {
        var c = $"x-auth-app={_appCode}";
        if (!string.IsNullOrEmpty(_appBrand)) c += $"; x-auth-brand={_appBrand}";
        return c;
    }

    private async Task<JsonElement> RequestAsync(
        HttpMethod method, string path, object? body = null, string? extraCookie = null)
    {
        var req = new HttpRequestMessage(method, $"{_baseUrl}{path}");
        req.Headers.TryAddWithoutValidation("Cookie",
            extraCookie != null ? $"{BuildCookie()}; {extraCookie}" : BuildCookie());

        if (body != null)
            req.Content = JsonContent.Create(body, options: JsonContext.Default);

        HttpResponseMessage resp;
        try
        {
            resp = await _http.SendAsync(req);
            resp.EnsureSuccessStatusCode();
        }
        catch (Exception ex)
        {
            throw new SeewoNetworkError($"网络请求失败: {ex.Message}");
        }

        var json = await resp.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(json);
        return doc.RootElement.Clone();
    }

    private static void RaiseForError(int code, string message, string? raw)
    {
        switch (code)
        {
            case 4906:
                throw new SeewoNeedCaptcha(message, raw);
            case 4908:
            case 4909:
                throw new SeewoAuthError($"账号或密码错误 ({code})", code, raw);
            default:
                throw new SeewoLoginError($"登录失败 [{code}]: {message}", code, raw);
        }
    }

    /// <summary>账号+密码登录，密码自动 MD5 哈希</summary>
    public Task<SeewoLoginResult> LoginAsync(
        string username,
        string password,
        string? captchaKey = null,
        string? captchaContent = null,
        string? phoneCountryCode = null)
        => LoginCoreAsync(username, SeewoCrypto.HashPassword(password), captchaKey, captchaContent, phoneCountryCode);

    /// <summary>使用已 MD5 哈希的密码登录</summary>
    public Task<SeewoLoginResult> LoginWithHashAsync(
        string username,
        string passwordHash,
        string? captchaKey = null,
        string? captchaContent = null,
        string? phoneCountryCode = null)
        => LoginCoreAsync(username, passwordHash, captchaKey, captchaContent, phoneCountryCode);

    private async Task<SeewoLoginResult> LoginCoreAsync(
        string username,
        string passwordHash,
        string? captchaKey,
        string? captchaContent,
        string? phoneCountryCode)
    {
        var body = new Dictionary<string, object?>
        {
            ["username"] = username,
            ["password"] = passwordHash,
        };

        if (!string.IsNullOrEmpty(captchaKey) && !string.IsNullOrEmpty(captchaContent))
            body["captcha"] = new { key = captchaKey, captcha = captchaContent };
        if (!string.IsNullOrEmpty(phoneCountryCode))
            body["phoneCountryCode"] = phoneCountryCode;

        var response = await RequestAsync(HttpMethod.Post, SeewoDefaults.LoginEndpoint, body);

        var errorCode = response.TryGetProperty("error_code", out var ec) && ec.TryGetInt32(out var c) ? c : 0;
        if (errorCode != 0)
        {
            var msg = response.TryGetProperty("message", out var em) && em.ValueKind == JsonValueKind.String
                ? em.GetString()!
                : "未知错误";
            RaiseForError(errorCode, msg, response.GetRawText());
        }

        var rawText = response.GetRawText();
        return SeewoLoginResult.FromJson(response, rawText);
    }

    /// <summary>通过 token 获取用户详情（含头像），失败返回 null</summary>
    public async Task<SeewoUserProfile?> GetUserInfoAsync(string token)
    {
        try
        {
            var response = await RequestAsync(HttpMethod.Get, SeewoDefaults.UserInfoEndpoint,
                extraCookie: $"x-auth-token={token}");
            return SeewoUserProfile.FromJson(response);
        }
        catch (SeewoNetworkError)
        {
            return null;
        }
    }

    /// <summary>通过 token 获取头像 URL</summary>
    public async Task<string?> GetAvatarAsync(string token)
    {
        var profile = await GetUserInfoAsync(token);
        return profile?.Avatar;
    }
}

// ── 便捷函数 ──────────────────────────────────────────

public static class Seewo
{
    /// <summary>一行登录，每次创建临时客户端。复用 session 请用 SeewoClient</summary>
    public static async Task<SeewoLoginResult> LoginAsync(
        string username,
        string password,
        string? captchaKey = null,
        string? captchaContent = null,
        string? phoneCountryCode = null,
        string baseUrl = SeewoDefaults.BaseUrl,
        string appCode = SeewoDefaults.AppCode)
    {
        using var client = new SeewoClient(baseUrl, appCode);
        return await client.LoginAsync(username, password, captchaKey, captchaContent, phoneCountryCode);
    }
}

// ── JsonContext ─────────────────────────────────────

file static class JsonContext
{
    public static readonly JsonSerializerOptions Default = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };
}
