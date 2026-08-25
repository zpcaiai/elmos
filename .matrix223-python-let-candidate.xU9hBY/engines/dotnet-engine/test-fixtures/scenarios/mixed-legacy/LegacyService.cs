using Microsoft.Win32;
using System.ServiceModel;

[ServiceContract]
public interface ILegacyService { [OperationContract] string Read(); }
public sealed class LegacyService : ILegacyService { public string Read() => Registry.GetValue("HKEY_LOCAL_MACHINE\\Software\\ELMOS", "value", "missing")?.ToString() ?? "missing"; }
