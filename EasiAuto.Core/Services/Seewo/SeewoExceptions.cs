namespace EasiAuto.Core.Services.Seewo;

// ── 异常 ────────────────────────────────────────────

public class SeewoLoginError : Exception
{
    public int Code { get; }
    public string? RawResponse { get; }

    public SeewoLoginError(string message, int code = -1, string? response = null)
        : base(message)
    {
        Code = code;
        RawResponse = response;
    }
}

public class SeewoAuthError : SeewoLoginError
{
    public SeewoAuthError(string message, int code = -1, string? response = null)
        : base(message, code, response) { }
}

public class SeewoNetworkError : SeewoLoginError
{
    public SeewoNetworkError(string message)
        : base(message) { }
}

public class SeewoNeedCaptcha : SeewoLoginError
{
    public SeewoNeedCaptcha(string message = "需要验证码", string? response = null)
        : base(message, 4906, response) { }
}
