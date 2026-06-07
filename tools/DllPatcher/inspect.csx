#r "nuget: dnlib, 4.5.0"
using dnlib.DotNet;
using dnlib.DotNet.Emit;

var mod = ModuleDefMD.Load(@"G:\Downloads\easiauto\EasiNote.Account.dll");
foreach (var type in mod.GetTypes()) {
    if (type.Name == "CloudLoginProvider") {
        foreach (var m in type.Methods) {
            if (m.Name == "WebLogoutAsync") {
                Console.WriteLine($"Instructions: {m.Body.Instructions.Count}");
                foreach (var instr in m.Body.Instructions) {
                    Console.WriteLine($"  {instr.OpCode} {instr.Operand?.GetType().Name} {instr.Operand}");
                }
            }
        }
    }
}
