namespace EasiAuto.Core.Models.Login;

public enum LoginStatus
{
    Success,
    Failed,
    Canceled
}

public record LoginResult
{
    public LoginStatus Status { get; init; }
    public string? ErrorMessage { get; init; }

    private LoginResult(LoginStatus status, string? errorMessage = null)
    {
        Status = status;
        ErrorMessage = errorMessage;
    }

    public static LoginResult Success() => new(LoginStatus.Success);

    public static LoginResult Failed(string errorMessage) => new(LoginStatus.Failed, errorMessage);

    public static LoginResult Canceled(string? errorMessage = null) => new(LoginStatus.Canceled, errorMessage);

    public bool IsSuccess => Status == LoginStatus.Success;
    public bool IsFailed => Status == LoginStatus.Failed;
    public bool IsCanceled => Status == LoginStatus.Canceled;
}