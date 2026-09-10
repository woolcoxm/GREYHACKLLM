using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using BepInEx;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace GreyLLMHook;

/// <summary>
/// TCP server on 127.0.0.1 speaking newline-delimited JSON requests.
/// Every request is executed on the Unity main thread (the same thread the
/// game performs its own filesystem work on), so the game's data structures
/// are touched safely.
/// </summary>
public class HookServer
{
    private readonly int _port;
    private TcpListener _listener;
    private Thread _acceptThread;
    private volatile bool _running;

    public HookServer(int port)
    {
        _port = port;
    }

    public void Start()
    {
        _running = true;
        _listener = new TcpListener(IPAddress.Loopback, _port);
        _listener.Start();
        _acceptThread = new Thread(AcceptLoop) { IsBackground = true };
        _acceptThread.Start();
    }

    public void Stop()
    {
        _running = false;
        try
        {
            _listener?.Stop();
        }
        catch
        {
        }
    }

    private void AcceptLoop()
    {
        while (_running)
        {
            TcpClient client;
            try
            {
                client = _listener.AcceptTcpClient();
            }
            catch (SocketException)
            {
                break;
            }
            catch (ObjectDisposedException)
            {
                break;
            }
            var thread = new Thread(() => HandleClient(client)) { IsBackground = true };
            thread.Start();
        }
    }

    private void HandleClient(TcpClient client)
    {
        try
        {
            client.NoDelay = true;
            client.ReceiveTimeout = 15 * 60 * 1000;
            client.SendTimeout = 15 * 60 * 1000;
            using var stream = client.GetStream();
            using var reader = new StreamReader(stream, Encoding.UTF8);
            using var writer = new StreamWriter(stream, new UTF8Encoding(false)) { AutoFlush = true };
            string line;
            while (_running && (line = reader.ReadLine()) != null)
            {
                if (line.Trim().Length == 0)
                {
                    continue;
                }
                var response = Dispatch(line);
                writer.WriteLine(JsonConvert.SerializeObject(response, Formatting.None));
            }
        }
        catch (Exception exc)
        {
            Plugin.Log.LogWarning($"client connection ended: {exc.Message}");
        }
        finally
        {
            try
            {
                client.Close();
            }
            catch
            {
            }
        }
    }

    /// <summary>
    /// Run the handler on the main thread and wait for the result.
    /// </summary>
    private JObject Dispatch(string line)
    {
        JObject request;
        try
        {
            request = JObject.Parse(line);
        }
        catch
        {
            return Error("invalid json");
        }

        var op = request.Value<string>("op") ?? "";
        var done = new AutoResetEvent(false);
        JObject response = null;
        Exception failure = null;

        try
        {
            ThreadingHelper.Instance.StartSyncInvoke(() =>
            {
                try
                {
                    response = Ops.Handle(request, op);
                }
                catch (Exception exc)
                {
                    failure = exc;
                }
                finally
                {
                    done.Set();
                }
            });
        }
        catch (Exception exc)
        {
            return Error($"dispatch failed: {exc.Message}");
        }

        if (!done.WaitOne(TimeSpan.FromSeconds(Math.Max(60, Plugin.MaxRunSeconds.Value + 30))))
        {
            return Error("handler timeout — main thread did not complete");
        }
        if (failure != null)
        {
            Plugin.Log.LogError($"op {op} failed: {failure}");
            return Error($"{failure.GetType().Name}: {failure.Message}");
        }
        return response ?? Error("no response");
    }

    public static JObject Ok()
    {
        return new JObject { ["ok"] = true };
    }

    public static JObject Error(string message)
    {
        return new JObject { ["ok"] = false, ["error"] = message };
    }
}
