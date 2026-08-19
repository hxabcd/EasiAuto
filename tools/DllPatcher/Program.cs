using System;
using System.IO;
using System.Linq;
using dnlib.DotNet;
using dnlib.DotNet.Emit;

class Program
{
    const string CloudNamespace = "Cvte.EasiNote.Account.Auth.Login.Cloud";
    const string CloudClass = "CloudLoginProvider";
    const string CloudMethod = "WebLogoutAsync";

    const string AuthNamespace = "Cvte.EasiNote.Account.Auth.LoginToken";
    const string TokenFactoryClass = "TokenFactory";
    const string TokenFactoryBuildMethod = "Build";
    const string TokenProviderClass = "TokenProvider";
    const string AuthTokenProviderInterface = "IAuthTokenProvider";

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

        string dllDir = Path.GetDirectoryName(dllPath) ?? ".";
        string backupPath = dllPath + ".bak";
        bool anyChanges = false;

        // ── Step 0: Check and restore Newtonsoft.Json.dll if tampered ──
        string newtonsoftPath = Path.Combine(dllDir, "Newtonsoft.Json.dll");
        string newtonsoftBakPath = newtonsoftPath + ".bak";
        if (File.Exists(newtonsoftPath) && File.Exists(newtonsoftBakPath))
        {
            // Quick check: does the DLL contain "StartBridge" reference?
            var newtonsoftBytes = File.ReadAllBytes(newtonsoftPath);
            bool hasStartBridge = false;
            for (int i = 0; i < newtonsoftBytes.Length - 10; i++)
            {
                if (newtonsoftBytes[i] == 'S' && newtonsoftBytes[i+1] == 't' &&
                    newtonsoftBytes[i+2] == 'a' && newtonsoftBytes[i+3] == 'r' &&
                    newtonsoftBytes[i+4] == 't' && newtonsoftBytes[i+5] == 'B' &&
                    newtonsoftBytes[i+6] == 'r' && newtonsoftBytes[i+7] == 'i' &&
                    newtonsoftBytes[i+8] == 'd' && newtonsoftBytes[i+9] == 'g' &&
                    newtonsoftBytes[i+10] == 'e')
                {
                    hasStartBridge = true;
                    break;
                }
            }
            if (hasStartBridge)
            {
                Console.WriteLine("Newtonsoft.Json.dll appears patched (StartBridge found). Restoring from backup...");
                File.Copy(newtonsoftBakPath, newtonsoftPath, true);
                Console.WriteLine("Restored Newtonsoft.Json.dll from backup.");
            }
        }

        // ── Step 1: Load EasiNote.Account.dll ────────────────────────
        var dllBytes = File.ReadAllBytes(dllPath);
        var mod = ModuleDefMD.Load(dllBytes);

        try
        {
            var (cloudType, cloudMethod) = FindMethod(mod, CloudNamespace, CloudClass, CloudMethod);
            if (cloudMethod == null)
            {
                Console.Error.WriteLine($"Target method {CloudClass}.{CloudMethod} not found.");
                return 1;
            }

            // ── Step 2: Restore any previous logout interception ──
            bool restoredCloudPatch = false;
            if (IsOldUnconditionalPatch(cloudMethod.Body) || IsNewPatch(cloudMethod.Body))
            {
                Console.WriteLine("Detected logout interception patch. Restoring from backup...");
                if (!File.Exists(backupPath))
                {
                    Console.Error.WriteLine("No backup file found, cannot restore.");
                    return 1;
                }
                File.Copy(backupPath, dllPath, true);

                // Reload
                mod.Dispose();
                var restoredBytes = File.ReadAllBytes(dllPath);
                mod = ModuleDefMD.Load(restoredBytes);
                (cloudType, cloudMethod) = FindMethod(mod, CloudNamespace, CloudClass, CloudMethod);
                if (cloudMethod == null) return 1;

                if (IsOldUnconditionalPatch(cloudMethod.Body) || IsNewPatch(cloudMethod.Body))
                {
                    Console.Error.WriteLine("After restore, logout interception still exists. Aborting.");
                    return 1;
                }
                Console.WriteLine("Restored.");
                restoredCloudPatch = true;
            }

            // ── Step 3: Keep CloudLoginProvider.WebLogoutAsync original ──
            bool patchFailed = false;

            // ── Step 4: Apply TokenFactory.Build StartBridge patch ───
            if (!PatchTokenFactoryBuild(mod, dllDir, out var tokenFactoryChanged))
            {
                patchFailed = true;
            }
            anyChanges = restoredCloudPatch || tokenFactoryChanged;

            if (patchFailed)
            {
                Console.Error.WriteLine("Patch failed; output was not written.");
                return 1;
            }

            // ── Step 5: Write output ─────────────────────────────────
            if (anyChanges)
            {
                if (dryRun)
                {
                    string dryPath = dllPath + ".patched";
                    mod.Write(dryPath);
                    Console.WriteLine($"[DRY RUN] Written to: {dryPath}");
                }
                else
                {
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
            }
            else
            {
                Console.WriteLine("No changes needed.");
            }

            return 0;
        }
        finally
        {
            mod.Dispose();
        }
    }

    // ── 辅助：定位目标方法 ──────────────────────────────────────────
    static (TypeDef?, MethodDef?) FindMethod(ModuleDefMD mod, string ns, string cls, string method)
    {
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == ns && type.Name == cls)
            {
                foreach (var m in type.Methods)
                {
                    if (m.Name == method && m.HasBody && m.Body != null)
                        return (type, m);
                }
                return (type, null);
            }
        }
        return (null, null);
    }

    // ── 检测：旧版无条件补丁（2条指令: ldsfld CompletedTask; ret）──
    static bool IsOldUnconditionalPatch(CilBody body)
    {
        var instrs = body.Instructions;
        if (instrs.Count == 2)
        {
            var first = instrs[0];
            var second = instrs[1];
            if (first.OpCode == OpCodes.Ldsfld && second.OpCode == OpCodes.Ret)
            {
                if (first.Operand is IFullName fn && fn.FullName.Contains("Task::CompletedTask"))
                    return true;
            }
        }
        return false;
    }

    // ── 检测：是否已经是新版 CloudLoginProvider 补丁 ──────────────────
    static bool IsNewPatch(CilBody body)
    {
        foreach (var instr in body.Instructions)
        {
            if (instr.OpCode == OpCodes.Call && instr.Operand is IMethodDefOrRef m
                && m.Name == "IsTokenLoggedByProcess")
                return true;
        }
        return false;
    }

    // ── 应用 CloudLoginProvider.WebLogoutAsync 补丁（仅修改内存）──
    static bool ApplyCloudLoginPatch(ModuleDefMD mod, MethodDef targetMethod, string dllDir)
    {
        var body = targetMethod.Body;
        var originalInstructions = body.Instructions.ToArray();
        var originalVariables = body.Variables.ToArray();
        var originalHandlers = body.ExceptionHandlers.ToArray();

        Console.WriteLine($"CloudLoginProvider original body: {originalInstructions.Length} instructions");

        // ── 加载 SeewoPipeBridge.IsTokenLoggedByProcess 引用 ──────
        string bridgePath = Path.Combine(dllDir, "SeewoPipeBridge.dll");
        if (!File.Exists(bridgePath))
        {
            Console.Error.WriteLine($"SeewoPipeBridge.dll not found at: {bridgePath}");
            return false;
        }

        IMethodDefOrRef bridgeMethodRef;
        using (var bridgeMod = ModuleDefMD.Load(bridgePath))
        {
            MethodDef bridgeMethod = null;
            foreach (var type in bridgeMod.GetTypes())
            {
                if (type.FullName == "SeewoPipeBridge.SeewoPipeBridge")
                {
                    foreach (var m in type.Methods)
                    {
                        if (m.Name == "IsTokenLoggedByProcess")
                        { bridgeMethod = m; break; }
                    }
                    break;
                }
            }
            if (bridgeMethod == null)
            {
                Console.Error.WriteLine("IsTokenLoggedByProcess not found in SeewoPipeBridge.");
                return false;
            }
            bridgeMethodRef = mod.Import(bridgeMethod);
        }
        Console.WriteLine($"Imported: {bridgeMethodRef.FullName}");

        // ── 找到 TokenFactory.AuthTokenProvider.CurrentToken ──────
        MethodDef getCurrentToken = FindCurrentTokenGetter(mod);
        if (getCurrentToken == null)
        {
            Console.Error.WriteLine("CurrentToken property not found.");
            return false;
        }

        // TokenFactory.get_AuthTokenProvider (static)
        MethodDef getAuthTokenProvider = null;
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == AuthNamespace && type.Name == TokenFactoryClass)
            {
                foreach (var m in type.Methods)
                {
                    if (m.Name == "get_AuthTokenProvider" && m.IsStatic)
                    { getAuthTokenProvider = m; break; }
                }
                break;
            }
        }
        if (getAuthTokenProvider == null)
        {
            Console.Error.WriteLine("TokenFactory.get_AuthTokenProvider not found.");
            return false;
        }

        var importedGetAuthTokenProvider = mod.Import(getAuthTokenProvider);
        var importedGetCurrentToken = mod.Import(getCurrentToken);
        Console.WriteLine($"Token chain: {importedGetAuthTokenProvider.FullName} -> {importedGetCurrentToken.FullName}");

        var corlib = mod.CorLibTypes;
        var taskTypeSig = new TypeRefUser(mod, "System.Threading.Tasks", "Task", corlib.AssemblyRef).ToTypeSig();
        var completedTaskField = new MemberRefUser(mod, "CompletedTask",
            new FieldSig(taskTypeSig), new TypeRefUser(mod, "System.Threading.Tasks", "Task", corlib.AssemblyRef));

        // ── 构建新方法体 ─────────────────────────────────────────
        body.Instructions.Clear();
        body.Variables.Clear();
        body.ExceptionHandlers.Clear();

        // IL:
        //   call TokenFactory.get_AuthTokenProvider()
        //   callvirt get_CurrentToken()
        //   call IsTokenLoggedByProcess(token)
        //   brfalse.s ORIGINAL
        //   ldsfld Task.CompletedTask
        //   ret
        // ORIGINAL:
        //   (original instructions)

        body.Instructions.Add(OpCodes.Call.ToInstruction(importedGetAuthTokenProvider));
        body.Instructions.Add(OpCodes.Callvirt.ToInstruction(importedGetCurrentToken));
        body.Instructions.Add(OpCodes.Call.ToInstruction(bridgeMethodRef));
        body.Instructions.Add(OpCodes.Brfalse_S.ToInstruction(Instruction.Create(OpCodes.Nop)));
        body.Instructions.Add(OpCodes.Ldsfld.ToInstruction(mod.Import(completedTaskField)));
        body.Instructions.Add(OpCodes.Ret.ToInstruction());

        // 克隆原始指令并建立映射
        var cloneMap = new Dictionary<Instruction, Instruction>();
        var jumpTarget = Instruction.Create(OpCodes.Nop);
        body.Instructions.Add(jumpTarget);
        foreach (var instr in originalInstructions)
        {
            var clone = instr.Clone();
            cloneMap[instr] = clone;
            body.Instructions.Add(clone);
        }

        // 修复我们的跳转
        body.Instructions[3].Operand = jumpTarget;

        // 修复原始指令内部的跳转目标
        foreach (var instr in body.Instructions)
        {
            if (instr.Operand is Instruction oldTarget && cloneMap.TryGetValue(oldTarget, out var newTarget))
                instr.Operand = newTarget;
            else if (instr.Operand is Instruction[] oldTargets)
            {
                var newTargets = new Instruction[oldTargets.Length];
                for (int i = 0; i < oldTargets.Length; i++)
                    newTargets[i] = cloneMap.TryGetValue(oldTargets[i], out var nt) ? nt : oldTargets[i];
                instr.Operand = newTargets;
            }
        }

        body.SimplifyBranches();
        body.OptimizeBranches();

        Console.WriteLine($"CloudLoginProvider new body: {body.Instructions.Count} instructions");
        Console.WriteLine("Logic: if IsTokenLoggedByProcess(token) → CompletedTask; else → original");
        return true;
    }

    // ── 查找 CurrentToken getter ──────────────────────────────────
    // TokenFactory.AuthTokenProvider 返回 TokenProvider (实现 IAuthTokenProvider)
    // CurrentToken 定义在 IAuthTokenProvider 接口上
    static MethodDef? FindCurrentTokenGetter(ModuleDefMD mod)
    {
        // 优先从 IAuthTokenProvider 接口查找
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == AuthNamespace && type.Name == AuthTokenProviderInterface
                && type.IsInterface)
            {
                foreach (var m in type.Methods)
                {
                    if (m.Name == "get_CurrentToken" && !m.IsStatic)
                        return m;
                }
            }
        }

        // 回退：从 TokenProvider 类查找
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == AuthNamespace && type.Name == TokenProviderClass)
            {
                foreach (var m in type.Methods)
                {
                    if (m.Name == "get_CurrentToken" && !m.IsStatic)
                        return m;
                }
            }
        }

        return null;
    }

    // ── 修补 TokenFactory.Build：在结尾添加 StartBridge 调用 ─────
    static bool PatchTokenFactoryBuild(ModuleDefMD mod, string dllDir, out bool changed)
    {
        changed = false;
        // 找到 TokenFactory.Build
        TypeDef tokenFactoryType = null;
        MethodDef buildMethod = null;
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == AuthNamespace && type.Name == TokenFactoryClass)
            {
                tokenFactoryType = type;
                foreach (var m in type.Methods)
                {
                    if (m.Name == TokenFactoryBuildMethod && m.HasBody && m.Body != null)
                    { buildMethod = m; break; }
                }
                break;
            }
        }

        if (tokenFactoryType == null)
        {
            Console.Error.WriteLine("TokenFactory type not found.");
            return false;
        }
        if (buildMethod == null)
        {
            Console.Error.WriteLine("TokenFactory.Build method not found.");
            return false;
        }

        // 检查是否已经修补过
        foreach (var instr in buildMethod.Body.Instructions)
        {
            if (instr.OpCode == OpCodes.Call && instr.Operand is IMethodDefOrRef m
                && m.Name == "StartBridge")
            {
                Console.WriteLine("TokenFactory.Build already patched with StartBridge, skipping.");
                return true;
            }
        }

        // ── 导入 SeewoPipeBridge.StartBridge ─────────────────────
        string bridgePath = Path.Combine(dllDir, "SeewoPipeBridge.dll");
        if (!File.Exists(bridgePath))
        {
            Console.Error.WriteLine($"SeewoPipeBridge.dll not found at: {bridgePath}");
            return false;
        }

        IMethodDefOrRef startBridgeRef;
        using (var bridgeMod = ModuleDefMD.Load(bridgePath))
        {
            MethodDef startBridgeMethod = null;
            foreach (var type in bridgeMod.GetTypes())
            {
                if (type.FullName == "SeewoPipeBridge.SeewoPipeBridge")
                {
                    foreach (var m in type.Methods)
                    {
                        if (m.Name == "StartBridge")
                        { startBridgeMethod = m; break; }
                    }
                    break;
                }
            }
            if (startBridgeMethod == null)
            {
                Console.Error.WriteLine("StartBridge not found in SeewoPipeBridge.");
                return false;
            }
            startBridgeRef = mod.Import(startBridgeMethod);
        }
        Console.WriteLine($"Imported: {startBridgeRef.FullName}");

        // ── 在 Build 方法的最后一个 ret 之前插入 StartBridge 调用 ──
        var body = buildMethod.Body;
        var instructions = body.Instructions;

        // 找到最后一个 ret 指令
        Instruction? lastRet = null;
        int lastRetIndex = -1;
        for (int i = 0; i < instructions.Count; i++)
        {
            if (instructions[i].OpCode == OpCodes.Ret)
            {
                lastRet = instructions[i];
                lastRetIndex = i;
            }
        }

        if (lastRet == null)
        {
            Console.Error.WriteLine("No ret instruction found in TokenFactory.Build.");
            return false;
        }

        // 在最后一个 ret 之前插入 call StartBridge()
        var callInstr = OpCodes.Call.ToInstruction(startBridgeRef);
        instructions.Insert(lastRetIndex, callInstr);
        changed = true;

        body.SimplifyBranches();
        body.OptimizeBranches();

        Console.WriteLine($"Patched TokenFactory.Build: added StartBridge() call before final ret (now {instructions.Count} instructions).");
        return true;
    }
}
