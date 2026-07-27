using System.Diagnostics;
using EasiAuto.Core.Abstraction.Login;
using EasiAuto.Core.Exceptions;
using EasiAuto.Core.Helpers;
using EasiAuto.Core.Models;
using EasiAuto.Core.Models.Login;
using Microsoft.Extensions.Logging;
using static EasiAuto.Core.Helpers.ProcessHelper;

namespace EasiAuto.Core.Services.Automation.Strategies;

public class LoginStatusEventArgs(string? task, string? progress) : EventArgs
{
    public string? Task { get; init; } = task;
    public string? Progress { get; init; } = progress;
}

/// <summary>
/// BeforeRun 传入的上下文。
/// </summary>
public record RunContext(string StrategyName);

/// <summary>
/// AfterRun 回调的结果摘要。
/// </summary>
public record RunResult(LoginStatus Status, string? ErrorMessage, int Attempts);

public abstract class BaseLoginStrategy(ILogger<BaseLoginStrategy> logger, LoginConfig loginConfig) : ILoginStrategy
{
    protected LoginConfig LoginConfig { get; } = loginConfig;
    protected ILogger<BaseLoginStrategy> logger = logger;

    public string StrategyName => GetStrategyName();
    protected abstract string GetStrategyName();

    // ──────────────────────────────────────────────
    //  调用方 hook（delegate）
    // ──────────────────────────────────────────────

    /// <summary>
    /// <see cref="Run"/> 执行前调用。返回 <c>false</c> 可取消执行。
    /// </summary>
    public Func<RunContext, bool?>? BeforeRun { get; set; }

    /// <summary>
    /// <see cref="Run"/> 执行后调用（无论成功、失败、取消）。
    /// </summary>
    public Action<RunResult>? AfterRun { get; set; }

    // ──────────────────────────────────────────────
    //  子类 hook（virtual）
    // ──────────────────────────────────────────────

    /// <summary>
    /// 在 <see cref="Prepare"/> 之前调用，子类可重写以进行额外准备。
    /// </summary>
    protected virtual void BeforePrepare()
    {
    }

    /// <summary>
    /// 在 <see cref="Login"/> 之前调用，子类可重写以进行额外准备。
    /// </summary>
    protected virtual void BeforeLogin(Process process, nint hwnd)
    {
    }

    /// <summary>
    /// 在 <see cref="Login"/> 成功之后调用。
    /// </summary>
    protected virtual void AfterLogin(Process process, nint hwnd)
    {
    }

    // ──────────────────────────────────────────────

    public event EventHandler<LoginStatusEventArgs>? LoginStatusUpdated;

    protected virtual void OnLoginStatusUpdated(LoginStatusEventArgs args) => LoginStatusUpdated?.Invoke(this, args);

    private string? _currentTask, _currentProgress;

    protected string? CurrentTask
    {
        get => _currentTask;
        set
        {
            if (value == _currentTask) return;
            _currentTask = value;
            logger.LogInformation("[任务更新] {message}", value);
            OnLoginStatusUpdated(new LoginStatusEventArgs(_currentTask, _currentProgress));
        }
    }

    protected string? CurrentProgress
    {
        get => _currentProgress;
        set
        {
            if (value == _currentProgress) return;
            _currentProgress = value;
            logger.LogDebug("[进度更新] {message}", value);
            OnLoginStatusUpdated(new LoginStatusEventArgs(_currentTask, _currentProgress));
        }
    }

    protected (string Path, EasiNotePathSource Source) GetEasiNotePath()
    {
        var useFallbackPath = false;
        var path = LoginConfig.EasiNote.UseAutoPath
            ? EasiNoteHelper.GetEasiNotePathFromReg()
            : LoginConfig.EasiNote.CustomPath;
        if (string.IsNullOrWhiteSpace(path))
        {
            path = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                @"Seewo\EasiNote5\swenlauncher\swenlauncher.exe"
            );
            useFallbackPath = true;
        }

        var source = (useFallbackPath, LoginConfig.EasiNote.UseAutoPath) switch
        {
            (true, _) => EasiNotePathSource.Auto,
            (false, true) => EasiNotePathSource.Custom,
            (false, false) => EasiNotePathSource.Default
        };
        return File.Exists(path) ? (path, source) : throw new FileNotFoundException("找不到希沃白板路径", path);
    }

    protected virtual string GetEasiNoteArgs()
    {
        return LoginConfig.EasiNote.Args;
    }

    protected abstract IReadOnlySet<Type> SupportedCredentials { get; }

    /// <summary>
    /// 检查凭据是否被当前策略支持。
    /// </summary>
    protected bool IsCredentialSupported(LoginCredential credential)
        => SupportedCredentials.Contains(credential.GetType());

    protected abstract bool CheckLoggedIn(LoginCredential credential);

    /// <summary>
    /// 已启动则重启，否则直接启动
    /// </summary>
    /// <param name="path">希沃白板主程序文件路径</param>
    /// <param name="processName">希沃白板进程名</param>
    /// <param name="waitTime">进程终止后的等待时间</param>
    protected Process RestartEasiNote(string path, string processName, double waitTime)
    {
        if (ProcessHelper.IsProcessRunning(processName))
        {
            logger.LogInformation("终止进程");
            ProcessHelper.StopProcess(processName);
            Sleep(waitTime);
        }

        if (LoginConfig.ShouldKillAgent)
        {
            logger.LogDebug("终止 EasiAgent 进程");
            ProcessHelper.StopProcess("EasiAgent");
        }

        logger.LogInformation("启动程序");
        var args = GetEasiNoteArgs();
        logger.LogDebug("路径：{path}，参数：{args}", path, args);

        if (!File.Exists(path))
        {
            throw new FileNotFoundException("希沃白板可执行文件不存在", path);
        }

        var process = ProcessHelper.StartProcess(processName, args);
        return process ?? throw new LoginException("启动希沃白板失败");
    }

    protected nint WaitForWindow(string windowTitle, double timeout, double interval)
    {
        double elapsed = 0;

        while (elapsed < timeout)
        {
            CurrentProgress = $"等待{windowTitle}出现 ({elapsed}/{timeout}s)";
            var hwnd = WindowHelper.GetWindowHandle(windowTitle);
            if (hwnd != nint.Zero)
            {
                return hwnd;
            }

            Sleep(interval);
            elapsed += interval;
        }

        throw new LoginException($"窗口在 {timeout} 秒内未打开");
    }

    private (Process EasiNoteProcess, nint EasiNoteHwnd) Prepare(LoginCredential credential)
    {
        CurrentProgress = "获取希沃白板目录";
        var (easiNotePath, easiNotePathSource) = GetEasiNotePath();
        var sourceText = easiNotePathSource switch
        {
            EasiNotePathSource.Auto => "自动获取",
            EasiNotePathSource.Custom => "自定义",
            EasiNotePathSource.Default => "默认",
            _ => "未知"
        };
        logger.LogDebug("获取到希沃白板路径: {path} (源: {source})", easiNotePath, sourceText);

        var isEasiNoteRunning = ProcessHelper.IsProcessRunning(LoginConfig.EasiNote.ProcessName);

        if (LoginConfig.ShouldSkipIfLoggedIn)
        {
            CurrentProgress = "检查登录状态";
            if (isEasiNoteRunning && CheckLoggedIn(credential))
            {
                throw new LoginCancelled("该账号已登录");
            }
        }

        CurrentProgress = isEasiNoteRunning ? "重启希沃白板" : "启动希沃白板";
        var process = RestartEasiNote(easiNotePath, LoginConfig.EasiNote.ProcessName, LoginConfig.Timeout.Terminate);

        var hwnd = WaitForWindow(
            LoginConfig.EasiNote.WindowTitle,
            LoginConfig.Timeout.LaunchPollingTimeout,
            LoginConfig.Timeout.LaunchPollingInterval
        );

        CurrentTask = "等待登录";
        CurrentProgress = "希沃白板已启动";
        Sleep(LoginConfig.Timeout.AfterLaunch);

        return (process, hwnd);
    }

    protected abstract void Login(LoginCredential rawCredential, Process easiNoteProcess, nint easiNoteHwnd);

    public LoginResult Run(LoginCredential credential)
    {
        // ── 凭据校验 ──
        if (!IsCredentialSupported(credential))
            return LoginResult.Failed(
                $"策略 '{StrategyName}' 不支持凭据类型 '{credential.GetType().Name}'");

        // ── BeforeRun ──
        if (BeforeRun?.Invoke(new RunContext(StrategyName)) == false)
            return LoginResult.Canceled("外部取消");

        var retries = 0;
        LoginResult result;

        while (true)
        {
            try
            {
                BeforePrepare();
                var (process, hwnd) = Prepare(credential);
                BeforeLogin(process, hwnd);
                Login(credential, process, hwnd);
                AfterLogin(process, hwnd);
                result = LoginResult.Success();
                break;
            }
            catch (LoginCancelled ex)
            {
                logger.LogInformation(ex, "登录被取消");
                result = LoginResult.Canceled(ex.Message);
                break;
            }
            catch (Exception ex)
            {
                if (ex is LoginException { IsRetryAllowed: false })
                {
                    logger.LogCritical(ex, "登录失败 (重试已禁用)");
                    result = LoginResult.Failed(ex.Message);
                    break;
                }

                if (retries++ < LoginConfig.MaxRetries)
                {
                    logger.LogError(ex, "登录失败, 将在 {time}s 后重试 ({retries}/{maxRetries})",
                        LoginConfig.RetryInterval, retries, LoginConfig.MaxRetries);
                    Sleep(LoginConfig.RetryInterval);
                    continue;
                }

                logger.LogCritical(ex, "{maxRetries} 次尝试均失败", LoginConfig.MaxRetries);
                result = LoginResult.Failed(ex.Message);
                break;
            }
        }

        // ── AfterRun ──
        AfterRun?.Invoke(new RunResult(result.Status, result.ErrorMessage, retries + 1));

        return result;
    }
}