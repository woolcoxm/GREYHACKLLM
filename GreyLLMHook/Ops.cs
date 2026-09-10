using System;
using System.Threading;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;
using HarmonyLib;
using Util;

namespace GreyLLMHook;

/// <summary>
/// Request handlers. All run on the main thread via HookServer.Dispatch.
/// </summary>
public static class Ops
{
    private static int _runCounter;
    private static readonly object RunGate = new object();
    private static bool _runInFlight;

    public static JObject Handle(JObject req, string op)
    {
        switch (op)
        {
            case "health":
                return Health();
            case "read":
                return Read(Str(req, "path"));
            case "write":
                return Write(Str(req, "path"), Str(req, "content"));
            case "append":
                return Append(Str(req, "path"), Str(req, "content"));
            case "exists":
                return Exists(Str(req, "path"));
            case "list":
                return List(Str(req, "path"));
            case "mkdir":
                return Mkdir(Str(req, "path"));
            case "delete":
                return Delete(Str(req, "path"));
            case "run":
                return Run(req);
            case "debug":
                return DebugFs();
            default:
                return HookServer.Error($"unknown op '{op}'");
        }
    }

    // ---- guards ---------------------------------------------------------

    private static PlayerServer PlayerOrError(out JObject error)
    {
        error = null;
        if (!Networking.IsSinglePlayer())
        {
            error = HookServer.Error("game is not in singleplayer — refusing");
            return null;
        }
        var player = Patches.Player ?? FindPlayer();
        if (player == null)
        {
            error = HookServer.Error("no player session — log into a singleplayer world first");
            return null;
        }
        return player;
    }

    /// <summary>
    /// Resolve the player from the server registry. More reliable than the
    /// ReceiveData patch: that loop starts at login, potentially before
    /// BepInEx loads us, so it may never be patched for this session.
    /// </summary>
    private static PlayerServer FindPlayer()
    {
        try
        {
            var listener = ServerListener.Singleton;
            if (listener == null)
            {
                return null;
            }
            var dict = AccessTools.Field(typeof(ServerListener), "players")
                .GetValue(listener) as System.Collections.IDictionary;
            if (dict == null)
            {
                return null;
            }
            foreach (System.Collections.DictionaryEntry entry in dict)
            {
                if (entry.Value is PlayerServer candidate && !candidate.exiting)
                {
                    return candidate;
                }
            }
        }
        catch (Exception exc)
        {
            Plugin.Log.LogWarning($"FindPlayer: {exc.Message}");
        }
        return null;
    }

    private static Computer ComputerOrError(out JObject error)
    {
        var player = PlayerOrError(out error);
        if (player == null)
        {
            return null;
        }
        var computer = player.GetComputer();
        if (computer == null)
        {
            error = HookServer.Error("player computer unavailable");
            return null;
        }
        return computer;
    }

    // ---- ops ------------------------------------------------------------

    private static JObject Health()
    {
        var player = Patches.Player ?? FindPlayer();
        var single = Networking.IsSinglePlayer();
        return new JObject
        {
            ["ok"] = true,
            ["singleplayer"] = single,
            ["session"] = player != null,
            ["busy"] = _runInFlight,
            ["hook"] = "1.0.0",
        };
    }

    private static string NormPath(string path)
    {
        path = (path ?? "").Replace('\\', '/').Trim();
        if (!path.StartsWith("/"))
        {
            path = "/" + path;
        }
        return path;
    }

    private static (string parent, string name) SplitPath(string path)
    {
        path = NormPath(path).TrimEnd('/');
        var idx = path.LastIndexOf('/');
        var name = path.Substring(idx + 1);
        var parent = idx <= 0 ? "/" : path.Substring(0, idx);
        return (parent, name);
    }

    private static JObject Read(string path)
    {
        path = NormPath(path);
        var computer = ComputerOrError(out var error);
        if (computer == null)
        {
            return error;
        }
        var file = computer.GetFileSystem().GetArchivo(path);
        if (file == null)
        {
            return HookServer.Error($"not found: {path}");
        }
        return new JObject
        {
            ["ok"] = true,
            ["content"] = file.GetContenido(),
            ["isFolder"] = false,
        };
    }

    private static JObject Write(string path, string content, bool append = false)
    {
        path = NormPath(path);
        var computer = ComputerOrError(out var error);
        if (computer == null)
        {
            return error;
        }
        // the game works save-through-database: restore, mutate, sync back.
        // without SyncFileSystemDB our change lives in a discarded snapshot.
        using (new FilesystemLock(computer.GetID(), "greyllm-hook"))
        {
        if (content == null)
        {
            content = "";
        }
        if (content.Length > 160000)
        {
            return HookServer.Error("content exceeds the game's 160,000 character limit");
        }
        var fs = computer.GetFileSystem();
        var file = fs.GetArchivo(path);
        if (file == null)
        {
            // create it in the parent folder
            var (parentPath, name) = SplitPath(path);
            var parent = fs.GetCarpeta(parentPath);
            if (parent == null)
            {
                return HookServer.Error($"parent folder not found: {parentPath}");
            }
            if (string.IsNullOrEmpty(name))
            {
                return HookServer.Error("invalid file name");
            }
            var initial = append ? content : "";
            // text file: this ctor family defaults to isBinario:true — pass false
            file = new FileSystem.Archivo(name, initial, "root",
                isBinario: false, saveToDB: true);
            parent.AddFile(file);
        }
        else if (append)
        {
            content = file.GetContenido() + content;
            if (content.Length > 160000)
            {
                return HookServer.Error("append would exceed the game's 160,000 character limit");
            }
        }
        file.SetContenido(content, saveToDB: true);
        }
        Database.Singleton.SyncFileSystemDB(computer, onlyFileSystem: true);
        return new JObject { ["ok"] = true, ["path"] = path };
    }

    private static JObject Append(string path, string content)
    {
        return Write(path, content, append: true);
    }

    private static JObject Exists(string path)
    {
        path = NormPath(path);
        var computer = ComputerOrError(out var error);
        if (computer == null)
        {
            return error;
        }
        var fs = computer.GetFileSystem();
        var file = fs.GetArchivo(path);
        var folder = fs.GetCarpeta(path);
        return new JObject
        {
            ["ok"] = true,
            ["exists"] = file != null || folder != null,
            ["isFolder"] = file == null && folder != null,
        };
    }

    private static JObject List(string path)
    {
        path = NormPath(path);
        var computer = ComputerOrError(out var error);
        if (computer == null)
        {
            return error;
        }
        var folder = computer.GetFileSystem().GetCarpeta(path);
        if (folder == null)
        {
            return HookServer.Error($"folder not found: {path}");
        }
        var entries = new JArray();
        foreach (var sub in folder.GetCarpetas())
        {
            entries.Add(new JObject { ["name"] = sub.GetNombre(), ["type"] = "dir" });
        }
        foreach (var f in folder.GetArchivos())
        {
            entries.Add(new JObject { ["name"] = f.GetNombre(), ["type"] = "file" });
        }
        return new JObject { ["ok"] = true, ["entries"] = entries };
    }

    private static JObject Mkdir(string path)
    {
        path = NormPath(path).TrimEnd('/');
        var computer = ComputerOrError(out var error);
        if (computer == null)
        {
            return error;
        }
        var fs = computer.GetFileSystem();
        if (fs.GetCarpeta(path) != null)
        {
            return new JObject { ["ok"] = true, ["existed"] = true };
        }
        var (parentPath, name) = SplitPath(path);
        var parent = fs.GetCarpeta(parentPath);
        if (parent == null)
        {
            return HookServer.Error($"parent folder not found: {parentPath}");
        }
        parent.AddFolder(new FileSystem.Carpeta(name, "root"));
        Database.Singleton.SyncFileSystemDB(computer, onlyFileSystem: true);
        return new JObject { ["ok"] = true };
    }

    private static JObject Delete(string path)
    {
        path = NormPath(path);
        var computer = ComputerOrError(out var error);
        if (computer == null)
        {
            return error;
        }
        var fs = computer.GetFileSystem();
        var file = fs.GetArchivo(path);
        var (parentPath, name) = SplitPath(path);
        var parent = fs.GetCarpeta(parentPath);
        if (file != null)
        {
            if (parent != null)
            {
                lock (parent.files)
                {
                    parent.files.Remove(file);
                }
            }
            Database.Singleton.SyncFileSystemDB(computer, onlyFileSystem: true);
            return new JObject { ["ok"] = true };
        }
        var folder = fs.GetCarpeta(path);
        if (folder != null)
        {
            if (folder.GetArchivos().Count > 0 || folder.GetCarpetas().Count > 0)
            {
                return HookServer.Error("folder not empty");
            }
            if (parent != null)
            {
                lock (parent.folders)
                {
                    parent.folders.Remove(folder);
                }
            }
            Database.Singleton.SyncFileSystemDB(computer, onlyFileSystem: true);
            return new JObject { ["ok"] = true };
        }
        return HookServer.Error($"not found: {path}");
    }

    // ---- script execution ------------------------------------------------

    private static JObject Run(JObject req)
    {
        var player = PlayerOrError(out var error);
        if (player == null)
        {
            return error;
        }
        var computer = player.GetComputer();

        var code = Str(req, "code");
        var timeoutSec = Math.Min(req.Value<int?>("timeout") ?? 120, Plugin.MaxRunSeconds.Value);
        if (string.IsNullOrEmpty(code))
        {
            return HookServer.Error("code is empty");
        }
        if (code.Length > 160000)
        {
            return HookServer.Error("code exceeds the game's 160,000 character limit");
        }

        lock (RunGate)
        {
            if (_runInFlight)
            {
                return HookServer.Error("a script is already running — one at a time");
            }
            _runInFlight = true;
        }

        var runId = Interlocked.Increment(ref _runCounter);
        var scriptName = $"greyllm-run-{runId}";
        var scriptPath = $"/root/{scriptName}.src";
        FileSystem.Archivo scriptFile = null;
        var windowPID = -1;

        try
        {
            // stage the script file in the player's filesystem
            var fs = computer.GetFileSystem();
            var rootFolder = fs.GetCarpeta("/root") ?? fs.GetCarpeta("/");
            scriptFile = new FileSystem.Archivo($"{scriptName}.src", code, "root",
                isBinario: false, saveToDB: true);
            rootFolder.AddFile(scriptFile);

            // register a process so the game tracks the program
            windowPID = computer.AddProcess(scriptName, "root", 0f,
                isScript: true, isTerminal: false, computer.GetID(), -1,
                isProtected: true, "", "", false, -1, "");

            // begin print capture for this window
            var buffer = new System.Text.StringBuilder();
            Patches.Prints[windowPID] = buffer;

            var parameters = (req["params"] as JArray ?? new JArray())
                .Select(p => p.ToString()).ToList();
            var command = new List<string> { scriptName };
            command.AddRange(parameters);

            var helper = player.greyScriptHelper;
            var runTask = helper.RunScriptFin(
                command,
                scriptFile.ID,
                0f,
                computer,
                "root",
                "/root",
                scriptPath,
                "",
                0,
                windowPID,
                null,
                false,
                null,
                false,
                false);

            var finished = TaskWait(runTask, TimeSpan.FromSeconds(timeoutSec));
            if (!finished)
            {
                KillRun(player, windowPID);
                var partial = buffer.ToString();
                return new JObject
                {
                    ["ok"] = false,
                    ["error"] = $"script timed out after {timeoutSec}s and was killed",
                    ["output"] = partial,
                };
            }

            Patches.Prints.TryRemove(windowPID, out _);
            Patches.Truncated.TryRemove(windowPID, out _);
            return new JObject
            {
                ["ok"] = true,
                ["output"] = buffer.ToString(),
                ["truncated"] = Patches.Truncated.TryRemove(windowPID, out var trunc) && trunc,
            };
        }
        catch (Exception exc)
        {
            Plugin.Log.LogError($"run failed: {exc}");
            return HookServer.Error($"{exc.GetType().Name}: {exc.Message}");
        }
        finally
        {
            Patches.Prints.TryRemove(windowPID, out _);
            Patches.Truncated.TryRemove(windowPID, out _);
            try
            {
                if (windowPID > 0)
                {
                    computer.CloseProgramClient(windowPID);
                }
            }
            catch
            {
            }
            try
            {
                if (scriptFile != null)
                {
                    var parent = scriptFile.GetParent();
                    if (parent != null)
                    {
                        lock (parent.files)
                        {
                            parent.files.Remove(scriptFile);
                        }
                    }
                }
            }
            catch
            {
            }
            lock (RunGate)
            {
                _runInFlight = false;
            }
        }
    }

    private static bool TaskWait(System.Threading.Tasks.Task task, TimeSpan timeout)
    {
        try
        {
            return task.Wait(timeout);
        }
        catch (AggregateException)
        {
            // the task throwing counts as "finished"; output/error reflect it
            return true;
        }
    }

    private static void KillRun(PlayerServer player, int windowPID)
    {
        try
        {
            var helper = player.greyScriptHelper;
            var dict = AccessTools.Field(typeof(GreyScriptHelperServer), "helperScript")
                .GetValue(helper) as System.Collections.IDictionary;
            if (dict != null && dict.Contains(windowPID))
            {
                var script = dict[windowPID];
                var launcher = AccessTools.Method(script.GetType(), "GetAppLauncher")
                    .Invoke(script, null) as AppLauncher;
                launcher?.KillScript(onlyCancel: false, isTerminal: true);
            }
        }
        catch (Exception exc)
        {
            Plugin.Log.LogWarning($"kill fallback: {exc.Message}");
            try
            {
                player.GetComputer().CloseProgramClient(windowPID);
            }
            catch
            {
            }
        }
    }

    private static JObject DebugFs()
    {
        var player = PlayerOrError(out var error);
        if (player == null)
        {
            return error;
        }
        var comp1 = player.GetComputer();
        var comp2 = player.GetComputer();
        var fs1 = comp1.GetFileSystem();
        var fs2 = comp2.GetFileSystem();
        var folder = fs1.GetCarpeta("/home/mark/.greyllm");
        if (folder == null)
        {
            return HookServer.Error("bridge folder missing");
        }
        var before = folder.GetArchivos().Count;
        var probe = new FileSystem.Archivo("dbgprobe.txt", "probe", "root",
            isBinario: false, saveToDB: true);
        folder.AddFile(probe);
        var after = folder.GetArchivos().Count;
        return new JObject
        {
            ["ok"] = true,
            ["comp1"] = comp1.GetHashCode(),
            ["comp2"] = comp2.GetHashCode(),
            ["fs1"] = fs1.GetHashCode(),
            ["fs2"] = fs2.GetHashCode(),
            ["folder"] = folder.GetHashCode(),
            ["before"] = before,
            ["after"] = after,
            ["viaSubArchivo"] = folder.GetSubArchivo("dbgprobe.txt") != null,
            ["viaGetArchivo"] = fs1.GetArchivo("/home/mark/.greyllm/dbgprobe.txt") != null,
            ["probeId"] = probe.ID,
            ["folderName"] = folder.GetNombre(),
            ["parentIsRoot"] = ReferenceEquals(folder.GetParent(), fs1.GetCarpeta("/home/mark")),
        };
    }

    private static string Str(JObject req, string key)
    {
        return req.Value<string>(key) ?? "";
    }
}
