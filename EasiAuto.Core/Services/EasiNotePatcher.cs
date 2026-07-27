using dnlib.DotNet;
using dnlib.DotNet.Emit;
using Microsoft.Extensions.Logging;

namespace EasiAuto.Core.Services;

/// <summary>
/// 希沃白板 DLL 修补服务。
/// 部署 SeewoPipeBridge.dll 并直接修补 EasiNote.Account.dll，
/// 使 EasiNote 在登录流程中加载 PipeBridge 以支持命名管道注入登录。
/// </summary>
public class EasiNotePatcher(ILogger<EasiNotePatcher> logger)
{
    // ═══════════════════════════════════════════════════════════
    // EasiNote 目标常量
    // ═══════════════════════════════════════════════════════════

    private const string CLOUD_NAMESPACE = "Cvte.EasiNote.Account.Auth.Login.Cloud";
    private const string CLOUD_CLASS = "CloudLoginProvider";
    private const string CLOUD_METHOD = "WebLogoutAsync";

    private const string AUTH_NAMESPACE = "Cvte.EasiNote.Account.Auth.LoginToken";
    private const string TOKEN_FACTORY_CLASS = "TokenFactory";
    private const string TOKEN_FACTORY_BUILD_METHOD = "Build";
    private const string TOKEN_PROVIDER_CLASS = "TokenProvider";
    private const string AUTH_TOKEN_PROVIDER_INTERFACE = "IAuthTokenProvider";

    /// <summary>SeewoPipeBridge 类型全名</summary>
    private const string BRIDGE_FULL_NAME = "SeewoPipeBridge.SeewoPipeBridge";

    private const string IS_TOKEN_LOGGED_BY_PROCESS_METHOD = "IsTokenLoggedByProcess";
    private const string START_BRIDGE_METHOD = "StartBridge";

    // ── 目录 / 文件常量 ──

    private const string EASI_NOTE_DIR_PREFIX = "EasiNote5_";
    private const string PIPE_BRIDGE_DLL = "SeewoPipeBridge.dll";
    private const string NEWTONSOFT_DLL = "Newtonsoft.Json.dll";
    private const string ACCOUNT_DLL = "EasiNote.Account.dll";

    /// <summary>vendor 资源目录（相对于应用程序基目录）</summary>
    private static readonly string VendorPath =
        Path.Combine(AppContext.BaseDirectory, "vendors");

    // ═══════════════════════════════════════════════════════════
    // 公共 API
    // ═══════════════════════════════════════════════════════════

    /// <summary>
    /// 检查 EasiNote 是否已修补。
    /// 判断条件：所有 EasiNote5_*/Main 目录下均存在 SeewoPipeBridge.dll。
    /// </summary>
    public bool IsEasiNotePatched(string easiNoteExePath)
    {
        var easiNoteBase = GetEasiNoteBase(easiNoteExePath);
        var targetDirs = FindEasiNoteVersionDirs(easiNoteBase);
        if (targetDirs.Count == 0)
            return false;

        return targetDirs.All(dir => File.Exists(Path.Combine(dir, PIPE_BRIDGE_DLL)));
    }

    /// <summary>
    /// 修补 EasiNote：部署 SeewoPipeBridge.dll 并修补 EasiNote.Account.dll。
    /// 已修补时直接返回 true。
    /// </summary>
    /// <returns>全部目标目录修补成功返回 true</returns>
    public bool PatchEasiNote(string easiNoteExePath)
    {
        if (IsEasiNotePatched(easiNoteExePath))
        {
            logger.LogInformation("希沃白板已修补");
            return true;
        }

        var easiNoteBase = GetEasiNoteBase(easiNoteExePath);
        var targetDirs = FindEasiNoteVersionDirs(easiNoteBase);

        if (targetDirs.Count == 0)
        {
            logger.LogWarning("无法在 {Base} 找到希沃白板版本目录", easiNoteBase);
            return false;
        }

        logger.LogInformation("找到 {Count} 个目标目录", targetDirs.Count);
        var allPatched = true;

        var srcBridgeDll = Path.Combine(VendorPath, PIPE_BRIDGE_DLL);

        foreach (var mainDir in targetDirs)
        {
            logger.LogInformation("处理: {MainDir}", mainDir);

            // ── 部署 SeewoPipeBridge.dll ──
            var dstBridgeDll = Path.Combine(mainDir, PIPE_BRIDGE_DLL);
            if (!DeployFile(srcBridgeDll, dstBridgeDll))
                allPatched = false;

            // ── 修补 EasiNote.Account.dll ──
            var targetDll = Path.Combine(mainDir, ACCOUNT_DLL);
            if (!File.Exists(targetDll))
            {
                logger.LogDebug("跳过不存在的: {Path}", targetDll);
                continue;
            }

            if (!PatchAccountDll(targetDll, mainDir))
                allPatched = false;
        }

        return allPatched;
    }

    /// <summary>
    /// 取消修补 EasiNote：移除 SeewoPipeBridge.dll，恢复 Newtonsoft.Json.dll 和
    /// EasiNote.Account.dll 的 .bak 备份。
    /// 未修补时直接返回 true。
    /// </summary>
    /// <returns>全部目标目录取消修补成功返回 true</returns>
    public bool UnpatchEasiNote(string easiNoteExePath)
    {
        if (!IsEasiNotePatched(easiNoteExePath))
        {
            logger.LogInformation("希沃白板未修补");
            return true;
        }

        var easiNoteBase = GetEasiNoteBase(easiNoteExePath);
        var targetDirs = FindEasiNoteVersionDirs(easiNoteBase);

        if (targetDirs.Count == 0)
        {
            logger.LogWarning("无法在 {Base} 找到希沃白板版本目录", easiNoteBase);
            return false;
        }

        logger.LogInformation("找到 {Count} 个目标目录", targetDirs.Count);
        var allUnpatched = true;

        foreach (var mainDir in targetDirs)
        {
            logger.LogInformation("处理: {MainDir}", mainDir);

            // ── 移除 SeewoPipeBridge.dll ──
            var pipeBridge = Path.Combine(mainDir, PIPE_BRIDGE_DLL);
            if (File.Exists(pipeBridge))
            {
                logger.LogInformation("移除: {Name}", PIPE_BRIDGE_DLL);
                try
                {
                    File.Delete(pipeBridge);
                }
                catch (Exception ex)
                {
                    logger.LogError(ex, "移除失败: {Path}", pipeBridge);
                    allUnpatched = false;
                    continue;
                }
            }

            // ── 恢复 Newtonsoft.Json.dll ──
            var newtonsoftDll = Path.Combine(mainDir, NEWTONSOFT_DLL);
            if (File.Exists(newtonsoftDll) && IsNewtonsoftPatched(newtonsoftDll))
            {
                if (!RestoreFromBak(newtonsoftDll))
                {
                    logger.LogWarning("{Name} 已被修改但无备份可用", NEWTONSOFT_DLL);
                    allUnpatched = false;
                }
            }

            // ── 恢复 EasiNote.Account.dll ──
            var accountDll = Path.Combine(mainDir, ACCOUNT_DLL);
            var accountBak = accountDll + ".bak";
            if (File.Exists(accountDll) && File.Exists(accountBak))
            {
                if (!RestoreFromBak(accountDll))
                {
                    logger.LogWarning("恢复 {Name} 失败", ACCOUNT_DLL);
                    allUnpatched = false;
                }
            }
        }

        return allUnpatched;
    }

    // ═══════════════════════════════════════════════════════════
    // 文件操作
    // ═══════════════════════════════════════════════════════════

    /// <summary>
    /// 部署单个文件。若目标文件已存在且内容一致则跳过；
    /// 不一致则创建 .bak 备份后覆盖写入。
    /// </summary>
    private bool DeployFile(string srcPath, string dstPath)
    {
        if (!File.Exists(srcPath))
        {
            logger.LogWarning("源文件不存在: {Src}", srcPath);
            return false;
        }

        if (File.Exists(dstPath))
        {
            try
            {
                if (File.ReadAllBytes(srcPath).SequenceEqual(File.ReadAllBytes(dstPath)))
                {
                    logger.LogDebug("文件内容一致，跳过: {Name}", Path.GetFileName(dstPath));
                    return true;
                }
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "读取文件失败");
                return false;
            }

            var bakPath = dstPath + ".bak";
            logger.LogInformation("创建备份: {Bak}", bakPath);
            try
            {
                File.Move(dstPath, bakPath);
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "备份失败: {Src} -> {Dst}", dstPath, bakPath);
                return false;
            }
        }

        try
        {
            var dir = Path.GetDirectoryName(dstPath);
            if (!string.IsNullOrEmpty(dir))
                Directory.CreateDirectory(dir);

            File.Copy(srcPath, dstPath);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "写入失败: {Dst}", dstPath);
            return false;
        }

        logger.LogInformation("已部署: {Dst}", dstPath);
        return true;
    }

    /// <summary>
    /// 从 .bak 备份恢复文件并删除备份。
    /// </summary>
    private bool RestoreFromBak(string filePath)
    {
        var bakPath = filePath + ".bak";
        if (!File.Exists(bakPath))
            return false;

        logger.LogInformation("从备份恢复: {Path}", filePath);
        try
        {
            File.Copy(bakPath, filePath, overwrite: true);
            File.Delete(bakPath);
            return true;
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "恢复失败: {Path}", filePath);
            return false;
        }
    }

    // ═══════════════════════════════════════════════════════════
    // 目录发现
    // ═══════════════════════════════════════════════════════════

    private static List<string> FindEasiNoteVersionDirs(string baseDir)
    {
        var dirs = new List<string>();

        if (!Directory.Exists(baseDir))
            return dirs;

        foreach (var child in Directory.GetDirectories(baseDir))
        {
            var childName = Path.GetFileName(child);
            if (childName.StartsWith(EASI_NOTE_DIR_PREFIX, StringComparison.OrdinalIgnoreCase))
            {
                var mainDir = Path.Combine(child, "Main");
                if (Directory.Exists(mainDir))
                    dirs.Add(mainDir);
            }
        }

        return dirs;
    }

    private static string GetEasiNoteBase(string easiNoteExePath)
    {
        var exeDir = Path.GetDirectoryName(Path.GetFullPath(easiNoteExePath))!;
        return Path.GetFullPath(Path.Combine(exeDir, "..", ".."));
    }

    // ═══════════════════════════════════════════════════════════
    // DLL 二进制检测
    // ═══════════════════════════════════════════════════════════

    private static bool IsNewtonsoftPatched(string dllPath)
    {
        try
        {
            var bytes = File.ReadAllBytes(dllPath);
            return ContainsByteSequence(bytes, "StartBridge"u8);
        }
        catch
        {
            return false;
        }
    }

    private static bool ContainsByteSequence(byte[] haystack, ReadOnlySpan<byte> needle)
    {
        if (needle.Length == 0 || haystack.Length < needle.Length)
            return false;

        for (var i = 0; i <= haystack.Length - needle.Length; i++)
        {
            if (haystack.AsSpan(i, needle.Length).SequenceEqual(needle))
                return true;
        }

        return false;
    }

    // ═══════════════════════════════════════════════════════════
    // DLL 修补核心（源自 DllPatcher/Program.cs）
    // ═══════════════════════════════════════════════════════════

    /// <summary>
    /// 对单个 EasiNote.Account.dll 执行修补。
    /// 包含 Newtonsoft.Json.dll 恢复、CloudLoginProvider 补丁和 TokenFactory 补丁。
    /// </summary>
    /// <param name="dllPath">EasiNote.Account.dll 的完整路径</param>
    /// <param name="dllDir">目标 DLL 所在目录（用于查找 SeewoPipeBridge.dll 和 Newtonsoft.Json.dll）</param>
    /// <returns>修补成功返回 true</returns>
    private bool PatchAccountDll(string dllPath, string dllDir)
    {
        // ── Step 0: 检查并恢复被注入的 Newtonsoft.Json.dll ──
        RestoreNewtonsoftIfPatched(dllDir);

        var backupPath = dllPath + ".bak";
        var dllBytes = File.ReadAllBytes(dllPath);

        // 加载目标程序集
        var mod = ModuleDefMD.Load(dllBytes);
        try
        {
            var (cloudType, cloudMethod) = FindMethod(mod, CLOUD_NAMESPACE, CLOUD_CLASS, CLOUD_METHOD);
            if (cloudMethod == null)
            {
                logger.LogError("未找到目标方法 {Class}.{Method}", CLOUD_CLASS, CLOUD_METHOD);
                return false;
            }

            // ── Step 1: 检测并处理旧版无条件补丁 ──
            if (IsOldUnconditionalPatch(cloudMethod.Body))
            {
                logger.LogInformation("检测到旧版无条件补丁，从备份恢复");
                if (!File.Exists(backupPath))
                {
                    logger.LogError("没有可用的备份文件，无法恢复");
                    return false;
                }

                File.Copy(backupPath, dllPath, overwrite: true);

                // 重新加载
                mod.Dispose();
                var restoredBytes = File.ReadAllBytes(dllPath);
                mod = ModuleDefMD.Load(restoredBytes);
                (cloudType, cloudMethod) = FindMethod(mod, CLOUD_NAMESPACE, CLOUD_CLASS, CLOUD_METHOD);
                if (cloudMethod == null)
                    return false;

                if (IsOldUnconditionalPatch(cloudMethod.Body))
                {
                    logger.LogError("恢复后仍检测到旧版补丁，中止");
                    return false;
                }

                logger.LogInformation("已从备份恢复");
            }

            var anyChanges = false;

            // ── Step 2: 应用 CloudLoginProvider.WebLogoutAsync 补丁 ──
            if (IsNewPatch(cloudMethod.Body))
            {
                logger.LogInformation("{Class}.{Method} 已修补，跳过", CLOUD_CLASS, CLOUD_METHOD);
            }
            else
            {
                anyChanges |= ApplyCloudLoginPatch(mod, cloudMethod, dllDir);
            }

            // ── Step 3: 应用 TokenFactory.Build StartBridge 补丁 ──
            anyChanges |= PatchTokenFactoryBuild(mod, dllDir);

            // ── Step 4: 写出 ──
            if (anyChanges)
            {
                // 创建备份（仅首次）
                if (!File.Exists(backupPath))
                {
                    File.Copy(dllPath, backupPath);
                    logger.LogInformation("已创建备份: {Backup}", backupPath);
                }

                // 原子写入：先写临时文件，再替换
                var tmpPath = Path.Combine(Path.GetTempPath(),
                    "EasiNotePatcher_" + Guid.NewGuid() + ".tmp");
                mod.Write(tmpPath);
                try
                {
                    File.Copy(tmpPath, dllPath, overwrite: true);
                    File.Delete(tmpPath);
                }
                catch
                {
                    File.Move(tmpPath, dllPath, overwrite: true);
                }

                logger.LogInformation("已修补: {Path}", dllPath);
            }
            else
            {
                logger.LogInformation("无需修改: {Path}", dllPath);
            }

            return true;
        }
        finally
        {
            mod.Dispose();
        }
    }

    /// <summary>
    /// 检查 Newtonsoft.Json.dll 是否被注入（包含 StartBridge 引用），若是则从 .bak 恢复。
    /// </summary>
    private void RestoreNewtonsoftIfPatched(string dllDir)
    {
        var newtonsoftPath = Path.Combine(dllDir, NEWTONSOFT_DLL);
        var newtonsoftBakPath = newtonsoftPath + ".bak";

        if (!File.Exists(newtonsoftPath) || !File.Exists(newtonsoftBakPath))
            return;

        if (IsNewtonsoftPatched(newtonsoftPath))
        {
            logger.LogInformation("Newtonsoft.Json.dll 已被注入（检测到 StartBridge），从备份恢复");
            File.Copy(newtonsoftBakPath, newtonsoftPath, overwrite: true);
            logger.LogInformation("已从备份恢复 Newtonsoft.Json.dll");
        }
    }

    // ── dnlib 符号定位 ──

    private static (TypeDef? Type, MethodDef? Method) FindMethod(
        ModuleDefMD mod, string ns, string cls, string method)
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

    // ── 旧版补丁检测（2 条指令: ldsfld CompletedTask; ret） ──

    private static bool IsOldUnconditionalPatch(CilBody body)
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

    // ── 新版补丁检测（已包含 IsTokenLoggedByProcess 调用） ──

    private static bool IsNewPatch(CilBody body)
    {
        foreach (var instr in body.Instructions)
        {
            if (instr.OpCode == OpCodes.Call && instr.Operand is IMethodDefOrRef m
                                               && m.Name == IS_TOKEN_LOGGED_BY_PROCESS_METHOD)
                return true;
        }

        return false;
    }

    // ── CloudLoginProvider.WebLogoutAsync 补丁 ──

    private bool ApplyCloudLoginPatch(ModuleDefMD mod, MethodDef targetMethod, string dllDir)
    {
        var body = targetMethod.Body;
        var originalInstructions = body.Instructions.ToArray();
        var originalVariables = body.Variables.ToArray();
        var originalHandlers = body.ExceptionHandlers.ToArray();

        logger.LogDebug("CloudLoginProvider 原始方法体: {Count} 条指令", originalInstructions.Length);

        // ── 导入 SeewoPipeBridge.IsTokenLoggedByProcess ──
        var bridgePath = Path.Combine(dllDir, PIPE_BRIDGE_DLL);
        if (!File.Exists(bridgePath))
        {
            logger.LogError("未找到 SeewoPipeBridge.dll: {Path}", bridgePath);
            return false;
        }

        IMethodDefOrRef bridgeMethodRef;
        using (var bridgeMod = ModuleDefMD.Load(bridgePath))
        {
            MethodDef? bridgeMethod = null;
            foreach (var type in bridgeMod.GetTypes())
            {
                if (type.FullName == BRIDGE_FULL_NAME)
                {
                    foreach (var m in type.Methods)
                    {
                        if (m.Name == IS_TOKEN_LOGGED_BY_PROCESS_METHOD)
                        {
                            bridgeMethod = m;
                            break;
                        }
                    }

                    break;
                }
            }

            if (bridgeMethod == null)
            {
                logger.LogError("在 SeewoPipeBridge 中未找到 IsTokenLoggedByProcess");
                return false;
            }

            bridgeMethodRef = mod.Import(bridgeMethod);
        }

        logger.LogDebug("已导入: {Method}", bridgeMethodRef.FullName);

        // ── 找到 TokenFactory.AuthTokenProvider.CurrentToken 调用链 ──
        var getCurrentToken = FindCurrentTokenGetter(mod);
        if (getCurrentToken == null)
        {
            logger.LogError("未找到 CurrentToken 属性");
            return false;
        }

        // TokenFactory.get_AuthTokenProvider (static)
        MethodDef? getAuthTokenProvider = null;
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == AUTH_NAMESPACE && type.Name == TOKEN_FACTORY_CLASS)
            {
                foreach (var m in type.Methods)
                {
                    if (m.Name == "get_AuthTokenProvider" && m.IsStatic)
                    {
                        getAuthTokenProvider = m;
                        break;
                    }
                }

                break;
            }
        }

        if (getAuthTokenProvider == null)
        {
            logger.LogError("未找到 TokenFactory.get_AuthTokenProvider");
            return false;
        }

        var importedGetAuthTokenProvider = mod.Import(getAuthTokenProvider);
        var importedGetCurrentToken = mod.Import(getCurrentToken);
        logger.LogDebug("Token 调用链: {AuthProvider} -> {CurrentToken}",
            importedGetAuthTokenProvider.FullName, importedGetCurrentToken.FullName);

        // Task.CompletedTask
        var corlib = mod.CorLibTypes;
        var taskTypeSig = new TypeRefUser(mod, "System.Threading.Tasks", "Task",
            corlib.AssemblyRef).ToTypeSig();
        var completedTaskField = new MemberRefUser(mod, "CompletedTask",
            new FieldSig(taskTypeSig),
            new TypeRefUser(mod, "System.Threading.Tasks", "Task", corlib.AssemblyRef));

        // ── 构建新方法体 ──
        // IL:
        //   call   TokenFactory.get_AuthTokenProvider()
        //   callvirt get_CurrentToken()
        //   call   IsTokenLoggedByProcess(token)
        //   brfalse.s ORIGINAL
        //   ldsfld Task.CompletedTask
        //   ret
        // ORIGINAL:
        //   (原始指令)
        body.Instructions.Clear();
        body.Variables.Clear();
        body.ExceptionHandlers.Clear();

        body.Instructions.Add(OpCodes.Call.ToInstruction(importedGetAuthTokenProvider));
        body.Instructions.Add(OpCodes.Callvirt.ToInstruction(importedGetCurrentToken));
        body.Instructions.Add(OpCodes.Call.ToInstruction(bridgeMethodRef));
        body.Instructions.Add(OpCodes.Brfalse_S.ToInstruction(Instruction.Create(OpCodes.Nop)));
        body.Instructions.Add(OpCodes.Ldsfld.ToInstruction(mod.Import(completedTaskField)));
        body.Instructions.Add(OpCodes.Ret.ToInstruction());

        // 克隆原始指令并修复跳转目标
        var cloneMap = new Dictionary<Instruction, Instruction>();
        var jumpTarget = Instruction.Create(OpCodes.Nop);
        body.Instructions.Add(jumpTarget);
        foreach (var instr in originalInstructions)
        {
            var clone = instr.Clone();
            cloneMap[instr] = clone;
            body.Instructions.Add(clone);
        }

        // 修正我们的条件跳转
        body.Instructions[3].Operand = jumpTarget;

        // 修正原始指令内部的跳转
        foreach (var instr in body.Instructions)
        {
            if (instr.Operand is Instruction oldTarget &&
                cloneMap.TryGetValue(oldTarget, out var newTarget))
                instr.Operand = newTarget;
            else if (instr.Operand is Instruction[] oldTargets)
            {
                var newTargets = new Instruction[oldTargets.Length];
                for (var i = 0; i < oldTargets.Length; i++)
                    newTargets[i] = cloneMap.TryGetValue(oldTargets[i], out var nt)
                        ? nt
                        : oldTargets[i];
                instr.Operand = newTargets;
            }
        }

        body.SimplifyBranches();
        body.OptimizeBranches();

        logger.LogDebug("CloudLoginProvider 新方法体: {Count} 条指令", body.Instructions.Count);
        logger.LogDebug("逻辑: if IsTokenLoggedByProcess(token) -> CompletedTask; else -> 原始逻辑");
        return true;
    }

    // ── 查找 CurrentToken getter ──

    private static MethodDef? FindCurrentTokenGetter(ModuleDefMD mod)
    {
        // 优先从 IAuthTokenProvider 接口查找
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == AUTH_NAMESPACE &&
                type.Name == AUTH_TOKEN_PROVIDER_INTERFACE &&
                type.IsInterface)
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
            if (type.Namespace == AUTH_NAMESPACE && type.Name == TOKEN_PROVIDER_CLASS)
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

    // ── TokenFactory.Build StartBridge 补丁 ──

    private bool PatchTokenFactoryBuild(ModuleDefMD mod, string dllDir)
    {
        // 找到 TokenFactory.Build
        TypeDef? tokenFactoryType = null;
        MethodDef? buildMethod = null;
        foreach (var type in mod.GetTypes())
        {
            if (type.Namespace == AUTH_NAMESPACE && type.Name == TOKEN_FACTORY_CLASS)
            {
                tokenFactoryType = type;
                foreach (var m in type.Methods)
                {
                    if (m.Name == TOKEN_FACTORY_BUILD_METHOD && m.HasBody && m.Body != null)
                    {
                        buildMethod = m;
                        break;
                    }
                }

                break;
            }
        }

        if (tokenFactoryType == null)
        {
            logger.LogError("未找到 TokenFactory 类型");
            return false;
        }

        if (buildMethod == null)
        {
            logger.LogError("未找到 TokenFactory.Build 方法");
            return false;
        }

        // 检查是否已修补
        foreach (var instr in buildMethod.Body.Instructions)
        {
            if (instr.OpCode == OpCodes.Call && instr.Operand is IMethodDefOrRef m
                                             && m.Name == START_BRIDGE_METHOD)
            {
                logger.LogInformation("TokenFactory.Build 已包含 StartBridge 调用，跳过");
                return false;
            }
        }

        // ── 导入 SeewoPipeBridge.StartBridge ──
        var bridgePath = Path.Combine(dllDir, PIPE_BRIDGE_DLL);
        if (!File.Exists(bridgePath))
        {
            logger.LogError("未找到 SeewoPipeBridge.dll: {Path}", bridgePath);
            return false;
        }

        IMethodDefOrRef startBridgeRef;
        using (var bridgeMod = ModuleDefMD.Load(bridgePath))
        {
            MethodDef? startBridgeMethod = null;
            foreach (var type in bridgeMod.GetTypes())
            {
                if (type.FullName == BRIDGE_FULL_NAME)
                {
                    foreach (var m in type.Methods)
                    {
                        if (m.Name == START_BRIDGE_METHOD)
                        {
                            startBridgeMethod = m;
                            break;
                        }
                    }

                    break;
                }
            }

            if (startBridgeMethod == null)
            {
                logger.LogError("在 SeewoPipeBridge 中未找到 StartBridge");
                return false;
            }

            startBridgeRef = mod.Import(startBridgeMethod);
        }

        logger.LogDebug("已导入: {Method}", startBridgeRef.FullName);

        // ── 在 Build 方法的最后一个 ret 之前插入 StartBridge 调用 ──
        var body = buildMethod.Body;
        var instructions = body.Instructions;

        // 找到最后一个 ret 指令
        Instruction? lastRet = null;
        var lastRetIndex = -1;
        for (var i = 0; i < instructions.Count; i++)
        {
            if (instructions[i].OpCode == OpCodes.Ret)
            {
                lastRet = instructions[i];
                lastRetIndex = i;
            }
        }

        if (lastRet == null)
        {
            logger.LogError("TokenFactory.Build 中未找到 ret 指令");
            return false;
        }

        // 在最后一个 ret 之前插入 call StartBridge()
        var callInstr = OpCodes.Call.ToInstruction(startBridgeRef);
        instructions.Insert(lastRetIndex, callInstr);

        body.SimplifyBranches();
        body.OptimizeBranches();

        logger.LogInformation(
            "已修补 TokenFactory.Build: 在 final ret 前插入了 StartBridge() 调用（共 {Count} 条指令）",
            instructions.Count);
        return true;
    }
}
