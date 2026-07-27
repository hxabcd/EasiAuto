namespace EasiAuto.Core.Exceptions;

public class LoginException : Exception
{
    public bool IsRetryAllowed { get; } = true;

    public LoginException()
    {
    }

    public LoginException(string message, bool isRetryAllowed = true) : base(message)
    {
        IsRetryAllowed = isRetryAllowed;
    }

    public LoginException(string message, Exception inner, bool isRetryAllowed = true) : base(message, inner)
    {
        IsRetryAllowed = isRetryAllowed;
    }
}