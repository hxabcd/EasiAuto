namespace EasiAuto.Core.Exceptions;

public class LoginCredentialTypeException : Exception
{
    public string? TypeName { get; }

    public LoginCredentialTypeException()
    {
    }

    public LoginCredentialTypeException(string message, string typeName) : base(message)
    {
        TypeName = typeName;
    }

    public LoginCredentialTypeException(string message, string typeName, Exception inner) : base(message, inner)
    {
        TypeName = typeName;
    }
}