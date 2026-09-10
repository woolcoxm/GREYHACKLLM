using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using HarmonyLib;

namespace GreyLLMHook;

/// <summary>
/// Harmony patches: session capture and print capture.
/// </summary>
public static class Patches
{
    /// <summary>
    /// The player's server instance, refreshed every time the game processes
    /// one of its own messages (i.e. constantly during play).
    /// </summary>
    public static volatile PlayerServer Player;

    /// <summary>
    /// Print capture buffers keyed by the window PID of an active run.
    /// </summary>
    public static readonly ConcurrentDictionary<int, StringBuilder> Prints =
        new ConcurrentDictionary<int, StringBuilder>();

    public static readonly ConcurrentDictionary<int, bool> Truncated =
        new ConcurrentDictionary<int, bool>();

    [HarmonyPrefix]
    [HarmonyPatch(typeof(PlayerServer), "ReceiveData")]
    private static void Prefix_ReceiveData(PlayerServer __instance)
    {
        // prefix only — never block the game's own processing
        if (Player != __instance)
        {
            Player = __instance;
            Plugin.Log.LogInfo("player session captured");
        }
    }

    [HarmonyPrefix]
    [HarmonyPatch(typeof(GreyScriptHelperServer), "SendPrintToClient")]
    private static void Prefix_SendPrintToClient(byte[] zipOutput, bool replaceText, int windowPID)
    {
        // prefix only — the game still displays the output normally
        if (!Prints.TryGetValue(windowPID, out var buffer))
        {
            return;
        }
        try
        {
            var text = StringCompressor.Unzip(zipOutput);
            if (replaceText)
            {
                // line-replacement (progress spinners): drop the last line
                RemoveLastLine(buffer);
            }
            lock (buffer)
            {
                if (buffer.Length > Plugin.MaxOutputKb.Value * 1024)
                {
                    Truncated[windowPID] = true;
                    return;
                }
                buffer.Append(text);
            }
        }
        catch
        {
            // never let capture break the game's output path
        }
    }

    private static void RemoveLastLine(StringBuilder buffer)
    {
        lock (buffer)
        {
            var trimmed = buffer.ToString().TrimEnd('\n', '\r');
            var idx = trimmed.LastIndexOf('\n');
            buffer.Clear();
            if (idx >= 0)
            {
                buffer.Append(trimmed.Substring(0, idx + 1));
            }
        }
    }
}

/// <summary>GZip helpers matching the game's print compression.</summary>
public static class StringCompressor
{
    public static string Unzip(byte[] bytes)
    {
        if (bytes == null || bytes.Length == 0)
        {
            return "";
        }
        using var input = new MemoryStream(bytes);
        using var gzip = new GZipStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        var chunk = new byte[4096];
        int read;
        while ((read = gzip.Read(chunk, 0, chunk.Length)) != 0)
        {
            output.Write(chunk, 0, read);
        }
        return Encoding.UTF8.GetString(output.ToArray());
    }
}
