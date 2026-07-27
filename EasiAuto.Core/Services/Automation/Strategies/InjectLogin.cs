using System.Diagnostics;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using EasiAuto.Core.Exceptions;
using EasiAuto.Core.Models;
using EasiAuto.Core.Models.Login;
using EasiAuto.Core.Services;
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
        var (easiNotePath, _) = GetEasiNotePath();
        if (!easiNotePatcher.IsEasiNotePatched(easiNotePath))
        {
            throw new LoginException("EasiNote 尚未修补，请先执行修补操作", isRetryAllowed: false);
        }
    }

    // ── 管道常量（与 SeewoPipeBridge.cs 保持一致） ──

    private const string TokenPipeName = "SeewoOpenTokenPipe";
    private const string LoginInfoPipeName = "SeewoLoginInfoPipe";
    private const int PipeMaxRetries = 15;
    private const int PipeRetryDelayMs = 1000;
    private const int PipeConnectTimeoutMs = 3000;

    // ── JSON 序列化选项 ──

    private static readonly JsonSerializerOptions PipeJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false,
    };

    // ── 管道协议模型 ──

    /// <summary>投递给 SeewoOpenTokenPipe 的登录载荷</summary>
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

    /// <summary>SeewoLoginInfoPipe 返回的当前登录信息</summary>
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

    /// <summary>SeewoOpenTokenPipe 可能返回的响应</summary>
    private record PipeLoginResponse
    {
        public bool Success { get; init; }
        public string? Message { get; init; }
        public string? ErrorDetail { get; init; }
    }

    // ── 抽象成员实现 ──

    protected override string GetStrategyName() => "Inject";

    protected override IReadOnlySet<Type> SupportedCredentials { get; }
        = new HashSet<Type> { typeof(PhonePasswordCredential), typeof(TokenCredential) };

    protected override bool CheckLoggedIn(LoginCredential credential)
    {
        var info = ReadLoginInfoFromPipe();
        if (info is not { StatusCode: 202 })
            return false;

        // 尝试获取目标 userId 做精确匹配
        var targetUserId = ResolveTargetUserId(credential);
        if (string.IsNullOrEmpty(targetUserId) || string.IsNullOrEmpty(info.UserId))
        {
            // 无法精确匹配时，视为未登录
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
        var payload = rawCredential switch
        {
            PhonePasswordCredential phoneCred => BuildPayloadFromPhonePassword(phoneCred),
            TokenCredential tokenCred => BuildPayloadFromToken(tokenCred),
            _ => throw new LoginCredentialTypeException("不支持的凭据种类", rawCredential.GetType().Name),
        };

        SendLoginViaPipe(payload);
    }

    // ── 凭据 -> 管道载荷 ──

    private PipeLoginPayload BuildPayloadFromPhonePassword(PhonePasswordCredential cred)
    {
        CurrentProgress = "通过账号密码获取登录令牌";
        logger.LogInformation("[Inject] 调用 Seewo API 登录, phone={Phone}", cred.Phone);

        SeewoLoginResult result;
        try
        {
            result = seewoClient.LoginAsync(cred.Phone, cred.Password).GetAwaiter().GetResult();
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

        if (string.IsNullOrEmpty(result.Token))
            throw new LoginException("Seewo API 未返回有效令牌");

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

        var profile = seewoClient.GetUserInfoAsync(cred.Token).GetAwaiter().GetResult();

        var nickName = profile?.NickName ?? "";
        var phone = profile?.Phone ?? "";

        if (profile != null)
            logger.LogDebug("[Inject] 获取到用户信息: nickName={NickName}, phone={Phone}", nickName, phone);
        else
            logger.LogWarning("[Inject] 无法通过 token 获取用户信息，将使用空字段投递");

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

    /// <summary>
    /// 通过命名管道 SeewoOpenTokenPipe 向 EasiNote 投递登录载荷。
    /// 与 Python qrcode.py 的 login() 方法逻辑一致。
    /// </summary>
    private void SendLoginViaPipe(PipeLoginPayload payload)
    {
        var json = JsonSerializer.Serialize(payload, PipeJsonOptions);
        logger.LogInformation("[Inject] 准备通过管道投递令牌, userId={UserId}, pipe={Pipe}",
            payload.UserId, TokenPipeName);

        CurrentProgress = "等待希沃白板管道就绪";

        for (var attempt = 1; attempt <= PipeMaxRetries; attempt++)
        {
            CurrentProgress = $"等待管道就绪 ({attempt}/{PipeMaxRetries})";

            try
            {
                using var pipe = new NamedPipeClientStream(".", TokenPipeName, PipeDirection.InOut);

                logger.LogDebug("[Inject] 第 {Attempt}/{MaxRetries} 次尝试连接管道...",
                    attempt, PipeMaxRetries);
                pipe.Connect(PipeConnectTimeoutMs);

                // 写入登录载荷（leaveOpen 防止 writer 关闭底层管道）
                using var writer = new StreamWriter(pipe, Encoding.UTF8, 1024, leaveOpen: true)
                    { AutoFlush = true };
                writer.WriteLine(json);

                logger.LogDebug("[Inject] 载荷已写入管道，等待响应...");

                // 尝试读取服务端响应（服务端为 PipeDirection.In 时不保证有响应）
                string? responseLine = null;
                try
                {
                    using var reader = new StreamReader(pipe, Encoding.UTF8, false, 1024, leaveOpen: true);
                    responseLine = reader.ReadLine();
                }
                catch (IOException)
                {
                    logger.LogDebug("[Inject] 管道在读取响应前关闭（服务端只读管道）");
                }
                catch (InvalidOperationException)
                {
                    logger.LogDebug("[Inject] 管道不支持读取（方向不匹配）");
                }

                if (!string.IsNullOrEmpty(responseLine))
                {
                    try
                    {
                        var response = JsonSerializer.Deserialize<PipeLoginResponse>(responseLine, PipeJsonOptions);
                        if (response is { Success: true })
                        {
                            logger.LogInformation("[Inject] 管道登录成功: {Message}",
                                response.Message ?? "");
                            CurrentProgress = "登录完成";
                            Sleep(1);
                            return;
                        }

                        var errMsg = response?.Message ?? "未知错误";
                        var errDetail = response?.ErrorDetail ?? "";
                        logger.LogError("[Inject] 管道登录失败: {Error} ({Detail})", errMsg, errDetail);
                        throw new LoginException($"管道登录失败: {errMsg}");
                    }
                    catch (JsonException ex)
                    {
                        logger.LogWarning("[Inject] 解析管道响应失败: {Error}, raw={Raw}",
                            ex.Message, responseLine);
                        throw new LoginException($"管道响应解析失败: {ex.Message}");
                    }
                }

                // 无响应或无法解析 → 视为成功（服务端接收后直接关闭管道）
                logger.LogInformation("[Inject] 管道投递完成（无显式响应），假设登录成功");
                CurrentProgress = "登录完成";
                Sleep(1);
                return;
            }
            catch (LoginException)
            {
                throw;
            }
            catch (TimeoutException)
            {
                logger.LogDebug("[Inject] 管道连接超时, 第 {Attempt}/{MaxRetries} 次重试...",
                    attempt, PipeMaxRetries);
            }
            catch (FileNotFoundException)
            {
                logger.LogDebug("[Inject] 管道尚未就绪, 第 {Attempt}/{MaxRetries} 次重试...",
                    attempt, PipeMaxRetries);
            }
            catch (IOException ex)
            {
                logger.LogDebug("[Inject] 管道 I/O 异常: {Error}, 第 {Attempt}/{MaxRetries} 次重试...",
                    ex.Message, attempt, PipeMaxRetries);
            }
            catch (UnauthorizedAccessException)
            {
                logger.LogDebug("[Inject] 管道访问被拒绝（权限不足），放弃重试");
                break;
            }

            if (attempt < PipeMaxRetries)
            {
                Sleep(PipeRetryDelayMs / 1000.0);
            }
        }

        throw new LoginException(
            $"命名管道 {TokenPipeName} 在 {PipeMaxRetries} 次尝试内未能就绪");
    }

    /// <summary>
    /// 通过 SeewoLoginInfoPipe 读取当前已登录账户信息。
    /// </summary>
    private PipeLoginInfo? ReadLoginInfoFromPipe()
    {
        try
        {
            using var pipe = new NamedPipeClientStream(".", LoginInfoPipeName, PipeDirection.InOut);
            pipe.Connect(PipeConnectTimeoutMs);

            using var writer = new StreamWriter(pipe, Encoding.UTF8, 1024, leaveOpen: true)
                { AutoFlush = true };
            writer.WriteLine("false");

            using var reader = new StreamReader(pipe, Encoding.UTF8, false, 1024, leaveOpen: true);
            var json = reader.ReadLine();

            if (string.IsNullOrEmpty(json))
                return null;

            return JsonSerializer.Deserialize<PipeLoginInfo>(json, PipeJsonOptions);
        }
        catch (TimeoutException)
        {
            logger.LogDebug("[Inject] LoginInfoPipe 连接超时");
            return null;
        }
        catch (FileNotFoundException)
        {
            logger.LogDebug("[Inject] LoginInfoPipe 不存在（EasiNote 未运行或未启动 PipeBridge）");
            return null;
        }
        catch (IOException ex)
        {
            logger.LogDebug("[Inject] LoginInfoPipe 读取异常: {Error}", ex.Message);
            return null;
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

    // ── 辅助方法 ──

    /// <summary>
    /// 尽量确定目标 userId，用于 CheckLoggedIn 的精确比对。
    /// 当前两种凭据类型均无法在登录前廉价获取 userId，
    /// 始终返回 null → CheckLoggedIn 无法做精确比对 → 不跳过登录。
    /// </summary>
    private static string? ResolveTargetUserId(LoginCredential credential) => null;

    /// <summary>返回第一个非空字符串</summary>
    private static string Coalesce(params string?[] values)
    {
        foreach (var v in values)
            if (!string.IsNullOrEmpty(v))
                return v;
        return "";
    }
}