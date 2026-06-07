using System;
using System.IO;
using System.Linq;
using dnlib.DotNet;
using dnlib.DotNet.Emit;

class Program
{
    const string TargetNamespace = "Cvte.EasiNote.Account.Auth.Login.Cloud";
    const string TargetClass = "CloudLoginProvider";
    const string TargetMethod = "WebLogoutAsync";

    static int Main(string[] args)
    {
        if (args.Length < 1)
        {
            Console.Error.WriteLine("Usage: DllPatcher <EasiNote.Account.dll> [--dry-run]");
            return 1;
        }

        string dllPath = Path.GetFullPath(args[0]);
        bool dryRun = args.Length > 1 && args[1] == "--dry-run";

        if (!File.Exists(dllPath))
        {
            Console.Error.WriteLine($"File not found: {dllPath}");
            return 1;
        }

        Console.WriteLine($"Loading: {dllPath}");

        var dllBytes = File.ReadAllBytes(dllPath);
        using var mod = ModuleDefMD.Load(dllBytes);

        TypeDef targetType = null;
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == TargetNamespace && type.Name == TargetClass)
            {
                targetType = type;
                break;
            }
        }

        if (targetType == null)
        {
            Console.Error.WriteLine($"Type not found: {TargetNamespace}.{TargetClass}");
            foreach (var type in mod.GetTypes())
            {
                if (type.Namespace is not null && type.Namespace.String.Contains("Cloud"))
                    Console.Error.WriteLine($"  {type.Namespace}.{type.Name}");
            }
            return 1;
        }

        Console.WriteLine($"Found type: {targetType.FullName}");

        MethodDef targetMethod = null;
        foreach (var method in targetType.Methods)
        {
            if (method.Name == TargetMethod)
            {
                targetMethod = method;
                break;
            }
        }

        if (targetMethod == null)
        {
            Console.Error.WriteLine($"Method not found: {TargetMethod}");
            Console.Error.WriteLine("Available methods:");
            foreach (var method in targetType.Methods)
                Console.Error.WriteLine($"  {method.Name} ({method.MethodSig})");
            return 1;
        }

        Console.WriteLine($"Found method: {targetMethod.Name} ({targetMethod.MethodSig})");

        if (!targetMethod.HasBody)
        {
            Console.Error.WriteLine("Method has no body (abstract/extern/PInvoke)");
            return 1;
        }

        var body = targetMethod.Body;
        if (body == null)
        {
            Console.Error.WriteLine("Method body is null");
            return 1;
        }

        bool alreadyPatched = false;
        var instrs = body.Instructions;
        if (instrs.Count == 2)
        {
            var first = instrs[0];
            var second = instrs[1];
            if (first.OpCode == OpCodes.Ldsfld && second.OpCode == OpCodes.Ret)
            {
                if (first.Operand is IFullName fn && fn.FullName.Contains("Task::CompletedTask"))
                {
                    alreadyPatched = true;
                }
            }
        }

        if (alreadyPatched)
        {
            Console.WriteLine("Already patched, skipping.");
            return 0;
        }

        Console.WriteLine($"Original body: {instrs.Count} instructions");

        var corlib = mod.CorLibTypes;
        var systemRuntime = corlib.AssemblyRef;
        var taskTypeRef = new TypeRefUser(mod, "System.Threading.Tasks", "Task", systemRuntime);
        var taskTypeSig = taskTypeRef.ToTypeSig();
        var completedTaskField = new MemberRefUser(mod, "CompletedTask", new FieldSig(taskTypeSig), taskTypeRef);
        var importedField = mod.Import(completedTaskField);

        body.Instructions.Clear();
        body.Variables.Clear();
        body.ExceptionHandlers.Clear();

        body.Instructions.Add(OpCodes.Ldsfld.ToInstruction(importedField));
        body.Instructions.Add(OpCodes.Ret.ToInstruction());

        body.SimplifyBranches();
        body.OptimizeBranches();

        Console.WriteLine("New body: ldsfld Task.CompletedTask; ret");

        if (dryRun)
        {
            string dryPath = dllPath + ".patched";
            mod.Write(dryPath);
            Console.WriteLine($"[DRY RUN] Written to: {dryPath}");
        }
        else
        {
            string backupPath = dllPath + ".bak";
            if (!File.Exists(backupPath))
            {
                File.Copy(dllPath, backupPath);
                Console.WriteLine($"Backup created: {backupPath}");
            }

            string tmpPath = Path.Combine(Path.GetTempPath(), "DllPatcher_" + Guid.NewGuid() + ".tmp");
            mod.Write(tmpPath);
            try
            {
                File.Copy(tmpPath, dllPath, true);
                File.Delete(tmpPath);
            }
            catch
            {
                File.Replace(tmpPath, dllPath, null);
            }
            Console.WriteLine($"Patched: {dllPath}");
        }

        return 0;
    }
}
