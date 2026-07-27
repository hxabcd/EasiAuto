using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using EasiAuto.Core.Exceptions;
using EasiAuto.Core.Models;
using EasiAuto.Core.Models.Login;
using EasiAuto.Core.Services.Seewo;
using Microsoft.Extensions.Logging;
using static EasiAuto.Core.Helpers.ProcessHelper;

namespace EasiAuto.Core.Services.Automation.Strategies;

/// <summary>
/// 通过命名管道向 EasiNote 进程注入登录令牌。
/// 与 EasiNote 内嵌的 SeewoPipeBridge 配合工作。
/// </summary>
public class InjectLogin(
    ILogger<BaseLoginStrategy> logger,
    LoginConfig loginConfig,
    SeewoClient seewoClient,
    EasiNotePatcher easiNotePatcher)
    : BaseLoginStrategy(logger, loginConfig)
{
    // ── 修补检查 ──

    protected override void BeforePrepare()
    {
        _context.Reset();
        var (easiNotePath, _) = GetEasiNotePath();
        if (!easiNotePatcher.IsEasiNotePatched(easiNotePath))
        {
            throw new LoginException("EasiNote 未修补", isRetryAllowed: false);
        }
    }

    // ── 管道常量（与 SeewoPipeBridge.cs 保持一致） ──

    private const string TOKEN_PIPE_NAME = "SeewoOpenTokenPipe";
    private const string LOGIN_INFO_PIPE_NAME = "SeewoLoginInfoPipe";
    private const int PIPE_MAX_RETRIES = 5;
    private const int PIPE_RETRY_DELAY_MS = 1000;
    private const int PIPE_CONNECT_TIMEOUT_MS = 3000;

    // ── JSON 序列化选项 ──

    private static readonly JsonSerializerOptions PipeJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false,
    };

    // ── 管道协议模型 ──

    private record PipeLoginPayload
    {
        public int StatusCode { get; init; } = 202;
        public string Token { get; init; } = "";
        public string UserId { get; init; } = "";
        public string UserName { get; init; } = "";
        public string NickName { get; init; } = "";
        public string Phone { get; init; } = "";
        public string Result { get; init; } = "https://e.seewo.com";
        public string Message { get; init; } = "客户端已扫码并确认登录";
    }

    private record PipeLoginInfo
    {
        public int StatusCode { get; init; }
        public string Token { get; init; } = "";
        public string UserId { get; init; } = "";
        public string UserName { get; init; } = "";
        public string NickName { get; init; } = "";
        public string Phone { get; init; } = "";
        public string Message { get; init; } = "";
    }

    private record PipeLoginResponse
    {
        public bool Success { get; init; }
        public string? Message { get; init; }
        public string? ErrorDetail { get; init; }
    }

    // ── Seewo 登录上下文 ──

    private readonly SeewoLoginContext _context = new(seewoClient, logger);

    // ── 抽象成员实现 ──

    protected override string GetStrategyName() => "Inject";

    protected override IReadOnlySet<Type> SupportedCredentials { get; }
        = new HashSet<Type> { typeof(PhonePasswordCredential), typeof(TokenCredential) };

    protected override bool CheckLoggedIn(LoginCredential credential)
    {
        var info = ReadLoginInfoFromPipe();
        if (info is not { StatusCode: 202 })
            return false;

        var targetUserId = ResolveTargetUserId(credential);
        if (string.IsNullOrEmpty(targetUserId) || string.IsNullOrEmpty(info.UserId))
        {
            logger.LogDebug("[Inject] 管道中有登录会话，但无法做 userId 精确比对 -> 视为未登录");
            return false;
        }

        var matched = string.Equals(targetUserId, info.UserId, StringComparison.OrdinalIgnoreCase);
        logger.LogDebug("[Inject] CheckLoggedIn: target={Target}, current={Current}, matched={Matched}",
            targetUserId, info.UserId, matched);
        return matched;
    }

    protected override void Login(LoginCredential rawCredential, Process easiNoteProcess, nint easiNoteHwnd)
    {
        var payload = BuildPayloadFromCredential(rawCredential);
        SendLoginViaPipe(payload);
    }

    // ── 凭据 -> 管道载荷 ──

    private PipeLoginPayload BuildPayloadFromCredential(LoginCredential credential)
    {
        return credential switch
        {
            PhonePasswordCredential phoneCred => BuildPayloadFromPhonePassword(phoneCred),
            TokenCredential tokenCred => BuildPayloadFromToken(tokenCred),
            _ => throw new LoginCredentialTypeException("不支持的凭据种类", credential.GetType().Name),
        };
    }

    private PipeLoginPayload BuildPayloadFromPhonePassword(PhonePasswordCredential cred)
    {
        CurrentProgress = "通过账号密码获取登录令牌";

        // 内部已处理缓存逻辑，网络异常会直接上抛
        var result = _context.GetOrCreateLoginResult(cred.Phone, cred.Password);

        // GetOrCreateLoginResult 成功返回时保证 Token 不为空，无需重复检查
        logger.LogInformation("[Inject] Seewo API 登录成功, userId={UserId}, nickName={NickName}",
            result.User.Uid, result.User.NickName);

        return new PipeLoginPayload
        {
            Token = result.Token,
            UserId = result.User.Uid,
            UserName = Coalesce(result.User.NickName, result.User.Username, result.User.Phone, ""),
            NickName = Coalesce(result.User.NickName, result.User.Username, ""),
            Phone = result.User.Phone,
        };
    }

    private PipeLoginPayload BuildPayloadFromToken(TokenCredential cred)
    {
        CurrentProgress = "通过令牌获取用户信息";
        logger.LogInformation("[Inject] 通过 token 获取用户详情");

        // 网络异常会直接上抛，由上层重试策略处理
        var profile = _context.GetOrCreateProfile(cred.Token);
        
        // 此时如果 profile 为 null，说明 API 调用成功但无数据，或存在逻辑冲突
        // 实际上 GetOrCreateProfile 内部如果遇到网络错误会抛异常，只有成功才返回结果
        
        var nickName = profile?.NickName ?? "";
        var phone = profile?.Phone ?? "";

        if (profile != null)
            logger.LogDebug("[Inject] 获取到用户信息: nickName={NickName}, phone={Phone}", nickName, phone);
        else
            logger.LogWarning("[Inject] API 返回成功但无用户信息，将使用空字段投递");

        return new PipeLoginPayload
        {
            Token = cred.Token,
            UserId = profile?.UserId ?? "",
            UserName = nickName,
            NickName = nickName,
            Phone = phone,
        };
    }

    // ── 管道通信核心 ──

    private void SendLoginViaPipe(PipeLoginPayload payload)
    {
        var json = JsonSerializer.Serialize(payload, PipeJsonOptions);
        logger.LogInformation("[Inject] 准备通过管道投递令牌, userId={UserId}, pipe={Pipe}",
            payload.UserId, TOKEN_PIPE_NAME);

        CurrentProgress = "等待希沃白板管道就绪";

        for (var attempt = 1; attempt <= PIPE_MAX_RETRIES; attempt++)
        {
            CurrentProgress = $"等待管道就绪 ({attempt}/{PIPE_MAX_RETRIES})";

            try
            {
                var (success, response) = TrySendAndReadResponse(TOKEN_PIPE_NAME, json);

                // 修正：只有 success=true（连接成功）才处理结果并返回
                if (success)
                {
                    if (TryParseResponse(response, out var parsed))
                    {
                        HandleLoginResponse(parsed);
                    }
                    else
                    {
                        // 连接成功但无响应或无法解析（服务端只读管道），视为成功
                        logger.LogInformation("[Inject] 管道投递完成（无显式响应），假设登录成功");
                    }

                    CurrentProgress = "登录完成";
                    Sleep(1);
                    return; // 成功退出
                }

                // success=false（连接超时/文件不存在等），继续下一次循环重试
                logger.LogDebug("[Inject] 管道连接失败，准备第 {Attempt} 次重试...", attempt + 1);
            }
            catch (UnauthorizedAccessException)
            {
                // 致命错误，无需重试
                throw new LoginException("管道访问被拒绝（权限不足）", isRetryAllowed: false);
            }
            // 其他未预期的异常直接上抛

            if (attempt < PIPE_MAX_RETRIES)
            {
                Sleep(PIPE_RETRY_DELAY_MS / 1000.0);
            }
        }

        throw new LoginException(
            $"命名管道 {TOKEN_PIPE_NAME} 在 {PIPE_MAX_RETRIES} 次尝试内未能就绪");
    }

    private PipeLoginInfo? ReadLoginInfoFromPipe()
    {
        try
        {
            var (success, response) = TrySendAndReadResponse(LOGIN_INFO_PIPE_NAME, "false");
            if (!success || string.IsNullOrEmpty(response))
                return null;

            return JsonSerializer.Deserialize<PipeLoginInfo>(response, PipeJsonOptions);
        }
        catch (UnauthorizedAccessException)
        {
            logger.LogDebug("[Inject] LoginInfoPipe 访问被拒绝（权限不足）");
            return null;
        }
        catch (JsonException ex)
        {
            logger.LogDebug("[Inject] LoginInfoPipe 解析失败: {Error}", ex.Message);
            return null;
        }
    }

    /// <summary>
    /// 通用管道通信方法。
    /// </summary>
    /// <returns>
    /// Success: true 表示连接成功（无论是否有响应）；false 表示连接失败（可重试错误）。
    /// Response: 服务端响应字符串，可能为 null。
    /// </returns>
    private (bool Success, string? Response) TrySendAndReadResponse(string pipeName, string message)
    {
        try
        {
            using var pipe = new NamedPipeClientStream(".", pipeName, PipeDirection.InOut);
            pipe.Connect(PIPE_CONNECT_TIMEOUT_MS);

            // 写入
            using (var writer = new StreamWriter(pipe, Encoding.UTF8, 1024, leaveOpen: true) { AutoFlush = true })
            {
                writer.WriteLine(message);
            }

            // 尝试读取
            try
            {
                using var reader = new StreamReader(pipe, Encoding.UTF8, false, 1024, leaveOpen: true);
                var response = reader.ReadLine();
                return (true, response);
            }
            catch (IOException)
            {
                // 写入成功但读取失败（服务端只写管道），视为连接成功
                return (true, null);
            }
            catch (InvalidOperationException)
            {
                // 方向不匹配，视为连接成功
                return (true, null);
            }
        }
        catch (TimeoutException)
        {
            return (false, null);
        }
        catch (FileNotFoundException)
        {
            return (false, null);
        }
        catch (IOException)
        {
            return (false, null);
        }
        // 注意：UnauthorizedAccessException 不在此处捕获，由调用方决定是否重试
    }

    private bool TryParseResponse(string? raw, [NotNullWhen(true)] out PipeLoginResponse? result)
    {
        result = null;
        if (string.IsNullOrEmpty(raw))
            return false;

        try
        {
            result = JsonSerializer.Deserialize<PipeLoginResponse>(raw, PipeJsonOptions);
            return result != null;
        }
        catch (JsonException ex)
        {
            logger.LogDebug("[Inject] 解析管道响应失败: {Error}, raw={Raw}", ex.Message, raw);
            return false;
        }
    }

    private void HandleLoginResponse(PipeLoginResponse response)
    {
        if (response is { Success: true })
        {
            logger.LogInformation("[Inject] 管道登录成功: {Message}", response.Message ?? "");
            return;
        }

        var errMsg = response?.Message ?? "未知错误";
        var errDetail = response?.ErrorDetail ?? "";
        logger.LogError("[Inject] 管道登录失败: {Error} ({Detail})", errMsg, errDetail);
        throw new LoginException($"管道登录失败: {errMsg}");
    }

    // ── 辅助方法 ──

    private string? ResolveTargetUserId(LoginCredential credential)
    {
        try
        {
            return credential switch
            {
                TokenCredential tokenCred => _context.GetOrCreateProfile(tokenCred.Token)?.UserId,
                PhonePasswordCredential phoneCred => _context.GetOrCreateLoginResult(phoneCred.Phone, phoneCred.Password).User.Uid,
                _ => null,
            };
        }
        catch (LoginException ex)
        {
            // CheckLoggedIn 阶段不应因 API 错误阻断登录流程
            logger.LogDebug(ex, "[Inject] 获取目标 userId 失败（{Type}），回退为不跳过", ex.GetType().Name);
            return null;
        }
    }

    private static string Coalesce(params string?[] values)
    {
        foreach (var v in values)
            if (!string.IsNullOrEmpty(v))
                return v;
        return "";
    }

    // ── 内部上下文类 ──

    private sealed class SeewoLoginContext
    {
        private readonly SeewoClient _client;
        private readonly ILogger _logger;

        private SeewoUserProfile? _cachedProfile;
        private SeewoLoginResult? _cachedLoginResult;

        public SeewoLoginContext(SeewoClient client, ILogger logger)
        {
            _client = client;
            _logger = logger;
        }

        public void Reset()
        {
            _cachedProfile = null;
            _cachedLoginResult = null;
        }

        /// <summary>
        /// 获取用户信息，如果缓存存在则直接返回。
        /// 注意：此方法会抛出 SeewoNetworkError 等异常，由调用方决定处理策略。
        /// </summary>
        public SeewoUserProfile? GetOrCreateProfile(string token)
        {
            if (_cachedProfile != null)
            {
                _logger.LogDebug("[Inject] 命中缓存：UserProfile");
                return _cachedProfile;
            }

            // 异常直接上抛，不在此处吞掉
            _cachedProfile = _client.GetUserInfoAsync(token).GetAwaiter().GetResult();
            return _cachedProfile;
        }

        /// <summary>
        /// 执行登录，如果缓存存在则直接返回。
        /// </summary>
        public SeewoLoginResult GetOrCreateLoginResult(string phone, string password)
        {
            if (_cachedLoginResult != null)
            {
                _logger.LogDebug("[Inject] 命中缓存：LoginResult");
                return _cachedLoginResult;
            }

            try
            {
                _logger.LogInformation("[Inject] 调用 Seewo API 登录, phone={Phone}", phone);
                var result = _client.LoginAsync(phone, password).GetAwaiter().GetResult();
                
                if (string.IsNullOrEmpty(result.Token))
                {
                    // 这种情况视为业务逻辑异常
                    throw new LoginException("Seewo API 未返回有效令牌");   
                }

                _cachedLoginResult = result;
                return result;
            }
            catch (SeewoNetworkError ex)
            {
                throw new LoginException($"Seewo API 网络错误: {ex.Message}");
            }
            catch (SeewoAuthError ex)
            {
                throw new LoginException($"Seewo API 认证失败: {ex.Message}", isRetryAllowed: false);
            }
            catch (SeewoLoginError ex)
            {
                throw new LoginException($"Seewo API 登录失败: {ex.Message}");
            }
        }
    }
}
