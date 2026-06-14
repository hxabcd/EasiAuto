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

        string backupPath = dllPath + ".bak";

        // ── 检测旧版无条件补丁 → 恢复后重新修补 ──────────────
        {
            var dllBytes = File.ReadAllBytes(dllPath);
            using var mod = ModuleDefMD.Load(dllBytes);

            var (targetType, targetMethod) = FindMethod(mod);
            if (targetMethod == null) return 1;

            if (IsOldUnconditionalPatch(targetMethod.Body))
            {
                Console.WriteLine("Detected OLD unconditional patch. Restoring from backup...");
                if (!File.Exists(backupPath))
                {
                    Console.Error.WriteLine("No backup file found, cannot restore.");
                    return 1;
                }
                File.Copy(backupPath, dllPath, true);

                // 验证恢复结果
                var restoredBytes = File.ReadAllBytes(dllPath);
                using var restoredMod = ModuleDefMD.Load(restoredBytes);
                var (rt, rm) = FindMethod(restoredMod);
                if (rm == null) return 1;

                if (IsOldUnconditionalPatch(rm.Body))
                {
                    Console.Error.WriteLine("After restore, still old patch. Aborting.");
                    return 1;
                }
                Console.WriteLine("Restored. Applying new patch...");
                return ApplyNewPatch(restoredMod, rm, dllPath, dryRun, backupPath);
            }

            if (IsNewPatch(targetMethod.Body))
            {
                Console.WriteLine("Already patched with new logic, skipping.");
                return 0;
            }

            return ApplyNewPatch(mod, targetMethod, dllPath, dryRun, backupPath);
        }
    }

    // ── 辅助：定位目标方法 ──────────────────────────────────
    static (TypeDef?, MethodDef?) FindMethod(ModuleDefMD mod)
    {
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == TargetNamespace && type.Name == TargetClass)
            {
                foreach (var method in type.Methods)
                {
                    if (method.Name == TargetMethod && method.HasBody && method.Body != null)
                        return (type, method);
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

    // ── 检测：是否已经是新版补丁 ──────────────────────────────
    static bool IsNewPatch(CilBody body)
    {
        // 新补丁的特征：包含对 IsTokenLoggedByProcess 的调用
        foreach (var instr in body.Instructions)
        {
            if (instr.OpCode == OpCodes.Call && instr.Operand is IMethodDefOrRef m
                && m.Name == "IsTokenLoggedByProcess")
                return true;
        }
        return false;
    }

    // ── 应用新版补丁 ──────────────────────────────────────────
    static int ApplyNewPatch(ModuleDefMD mod, MethodDef targetMethod, string dllPath, bool dryRun, string backupPath)
    {
        var body = targetMethod.Body;
        var originalInstructions = body.Instructions.ToArray();
        var originalVariables = body.Variables.ToArray();
        var originalHandlers = body.ExceptionHandlers.ToArray();

        Console.WriteLine($"Original body: {originalInstructions.Length} instructions");

        // ── 加载 SeewoPipeBridge 引用 ──────────────────────────
        string dllDir = Path.GetDirectoryName(dllPath) ?? ".";
        string bridgePath = Path.Combine(dllDir, "SeewoPipeBridge.dll");
        if (!File.Exists(bridgePath))
        {
            Console.Error.WriteLine($"SeewoPipeBridge.dll not found at: {bridgePath}");
            return 1;
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
                return 1;
            }
            bridgeMethodRef = mod.Import(bridgeMethod);
        }
        Console.WriteLine($"Imported: {bridgeMethodRef.FullName}");

        // ── 找到 TokenFactory.AuthTokenProvider.CurrentToken ────
        // TokenFactory 在 Cvte.EasiNote.Account.Auth.LoginToken 命名空间
        TypeDef tokenFactoryType = null;
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == "Cvte.EasiNote.Account.Auth.LoginToken"
                && type.Name == "TokenFactory")
            { tokenFactoryType = type; break; }
        }
        if (tokenFactoryType == null)
        {
            Console.Error.WriteLine("TokenFactory type not found.");
            return 1;
        }

        // TokenFactory.AuthTokenProvider (static property)
        MethodDef getAuthTokenProvider = null;
        foreach (var m in tokenFactoryType.Methods)
        {
            if (m.Name == "get_AuthTokenProvider" && m.IsStatic)
            { getAuthTokenProvider = m; break; }
        }
        if (getAuthTokenProvider == null)
        {
            Console.Error.WriteLine("TokenFactory.get_AuthTokenProvider not found.");
            return 1;
        }

        // AuthTokenProvider 的返回类型上的 CurrentToken 属性
        var authProviderTypeSig = getAuthTokenProvider.MethodSig.RetType;
        TypeDef authProviderTypeDef = null;
        if (authProviderTypeSig is ClassOrValueTypeSig classSig)
            authProviderTypeDef = classSig.TypeDef;
        // 如果 TypeDef 为 null，尝试通过 TypeDefOrRefSig 解析
        if (authProviderTypeDef == null && authProviderTypeSig is TypeDefOrRefSig typeDefOrRefSig)
        {
            if (typeDefOrRefSig.TypeDefOrRef is TypeRef tr)
                authProviderTypeDef = tr.Resolve();
            else if (typeDefOrRefSig.TypeDefOrRef is TypeDef td)
                authProviderTypeDef = td;
        }

        MethodDef getCurrentToken = null;
        if (authProviderTypeDef != null)
        {
            foreach (var m in authProviderTypeDef.Methods)
            {
                if (m.Name == "get_CurrentToken" && !m.IsStatic)
                { getCurrentToken = m; break; }
            }
        }
        if (getCurrentToken == null)
        {
            // 遍历所有类型找 CurrentToken 属性
            foreach (var type in mod.GetTypes())
            {
                foreach (var m in type.Methods)
                {
                    if (m.Name == "get_CurrentToken" && !m.IsStatic
                        && m.MethodSig.RetType.FullName == "System.String")
                    { getCurrentToken = m; break; }
                }
                if (getCurrentToken != null) break;
            }
        }
        if (getCurrentToken == null)
        {
            Console.Error.WriteLine("CurrentToken property not found.");
            return 1;
        }

        var importedGetAuthTokenProvider = mod.Import(getAuthTokenProvider);
        var importedGetCurrentToken = mod.Import(getCurrentToken);
        Console.WriteLine($"Token chain: {importedGetAuthTokenProvider.FullName} -> {importedGetCurrentToken.FullName}");

        var corlib = mod.CorLibTypes;
        var taskTypeSig = new TypeRefUser(mod, "System.Threading.Tasks", "Task", corlib.AssemblyRef).ToTypeSig();
        var completedTaskField = new MemberRefUser(mod, "CompletedTask",
            new FieldSig(taskTypeSig), new TypeRefUser(mod, "System.Threading.Tasks", "Task", corlib.AssemblyRef));

        // ── 构建新方法体 ──────────────────────────────────────
        body.Instructions.Clear();
        body.Variables.Clear();
        body.ExceptionHandlers.Clear();

        // IL:
        //   call TokenFactory.get_AuthTokenProvider()  ; static → IAuthTokenProvider
        //   callvirt IAuthTokenProvider.get_CurrentToken()  ; → string token
        //   call IsTokenLoggedByProcess(token)        ; → bool
        //   brfalse.s ORIGINAL                         ; if false, run original
        //   ldsfld Task.CompletedTask
        //   ret
        // ORIGINAL:
        //   (original instructions)

        body.Instructions.Add(OpCodes.Call.ToInstruction(importedGetAuthTokenProvider));    // TokenFactory.AuthTokenProvider
        body.Instructions.Add(OpCodes.Callvirt.ToInstruction(importedGetCurrentToken));     // .CurrentToken
        body.Instructions.Add(OpCodes.Call.ToInstruction(bridgeMethodRef));                  // IsTokenLoggedByProcess(token)
        body.Instructions.Add(OpCodes.Brfalse_S.ToInstruction(Instruction.Create(OpCodes.Nop))); // if false → original
        body.Instructions.Add(OpCodes.Ldsfld.ToInstruction(mod.Import(completedTaskField))); // Task.CompletedTask
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

        Console.WriteLine($"New body: {body.Instructions.Count} instructions");
        Console.WriteLine("Logic: if IsTokenLoggedByProcess(token) → CompletedTask; else → original");

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

        return 0;
    }
}
