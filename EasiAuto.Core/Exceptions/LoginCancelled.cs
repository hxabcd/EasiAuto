namespace EasiAuto.Core.Exceptions;

public class LoginCancelled : Exception
{
    public LoginCancelled() { }
    public LoginCancelled(string message) : base(message) { }
    public LoginCancelled(string message, Exception inner) : base(message, inner) { }
}
