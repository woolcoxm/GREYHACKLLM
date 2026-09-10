using BepInEx;
using BepInEx.Configuration;
using BepInEx.Logging;
using HarmonyLib;

namespace GreyLLMHook;

[BepInPlugin("greyllm.hook", "GreyLLM Hook", "1.0.0")]
public class Plugin : BaseUnityPlugin
{
    public static ManualLogSource Log;
    public static Harmony Harmony;
    public static ConfigEntry<int> Port;
    public static ConfigEntry<int> MaxRunSeconds;
    public static ConfigEntry<int> MaxOutputKb;

    public static HookServer Server;

    private void Awake()
    {
        Log = Logger;
        Port = Config.Bind("General", "Port", 7788, "Local TCP port (127.0.0.1 only)");
        MaxRunSeconds = Config.Bind("General", "MaxRunSeconds", 300, "Hard cap for a single script run");
        MaxOutputKb = Config.Bind("General", "MaxOutputKb", 1024, "Captured output cap per run");

        Harmony = new Harmony("greyllm.hook");
        Harmony.PatchAll();

        Server = new HookServer(Port.Value);
        Server.Start();

        Log.LogInfo($"GreyLLM Hook loaded — listening on 127.0.0.1:{Port.Value}");
    }

    private void OnDestroy()
    {
        Server?.Stop();
        Harmony?.UnpatchSelf();
        Log.LogInfo("GreyLLM Hook unloaded");
    }
}
