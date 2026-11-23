using System.Diagnostics;
using System.IO.Pipes;
using System.Text.Json;

namespace Sts2LiveBridge;

internal sealed record BridgeReply(bool Ok, object? Result, string? Error)
{
    public static BridgeReply Success(object result) => new(true, result, null);
    public static BridgeReply Failure(string error) => new(false, null, error);
}

internal sealed class BridgeRequest(string method, string? stateId, string? actionId)
{
    private readonly long _created = Stopwatch.GetTimestamp();
    private int _execution;
    public string Method { get; } = method;
    public string? StateId { get; } = stateId;
    public string? ActionId { get; } = actionId;
    public TaskCompletionSource<object> Completion { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public bool IsExpired => Stopwatch.GetElapsedTime(_created) >= TimeSpan.FromSeconds(3) || Volatile.Read(ref _execution) == -1;
    public bool TryBeginAction() => !IsExpired && Interlocked.CompareExchange(ref _execution, 1, 0) == 0;
    public void Expire() => Interlocked.CompareExchange(ref _execution, -1, 0);
}

internal sealed class PipeBridge(Func<BridgeRequest, object> handler, JsonSerializerOptions json)
{
    private const string PipeName = "sts2-live-bridge-v1";
    private const int RequestLimit = 4096;
    private const int ReplyLimit = 512 * 1024;
    private static readonly byte[] Newline = [(byte)'\n'];
    private BridgeRequest? _pending;

    public void Start() => _ = Task.Run(Serve);

    public void ProcessRequest()
    {
        var request = Interlocked.Exchange(ref _pending, null);
        if (request == null || request.IsExpired)
            return;
        try
        {
            request.Completion.TrySetResult(handler(request));
        }
        catch (Exception error)
        {
            Godot.GD.PushWarning($"[Sts2LiveBridge] {request.Method} failed: {error}");
            request.Completion.TrySetResult(BridgeReply.Failure("game_action_failed"));
        }
    }

    private async Task Serve()
    {
        while (true)
        {
            try
            {
                using var pipe = new NamedPipeServerStream(PipeName, PipeDirection.InOut, 1,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await pipe.WaitForConnectionAsync().ConfigureAwait(false);
                await HandleClient(pipe).ConfigureAwait(false);
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException or OperationCanceledException)
            {
                await Task.Delay(150).ConfigureAwait(false);
            }
        }
    }

    private async Task HandleClient(NamedPipeServerStream pipe)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(4));
        var request = await ReadRequest(pipe, timeout.Token).ConfigureAwait(false);
        object response = BridgeReply.Failure("invalid_request");
        if (request != null)
        {
            Interlocked.Exchange(ref _pending, request)?.Expire();
            try
            {
                response = await request.Completion.Task.WaitAsync(TimeSpan.FromSeconds(3), timeout.Token).ConfigureAwait(false);
            }
            catch (TimeoutException)
            {
                response = BridgeReply.Failure("game_thread_unavailable");
            }
            finally
            {
                request.Expire();
                Interlocked.CompareExchange(ref _pending, null, request);
            }
        }

        var serialized = JsonSerializer.SerializeToUtf8Bytes(response, json);
        if (serialized.Length >= ReplyLimit)
            serialized = JsonSerializer.SerializeToUtf8Bytes(BridgeReply.Failure("response_too_large"), json);
        await pipe.WriteAsync(serialized, timeout.Token).ConfigureAwait(false);
        await pipe.WriteAsync(Newline, timeout.Token).ConfigureAwait(false);
    }

    private static async Task<BridgeRequest?> ReadRequest(Stream pipe, CancellationToken token)
    {
        var buffer = new byte[RequestLimit];
        int used = 0;
        while (used < buffer.Length)
        {
            int count = await pipe.ReadAsync(buffer.AsMemory(used), token).ConfigureAwait(false);
            if (count == 0)
                return null;
            int end = Array.IndexOf(buffer, (byte)'\n', used, count);
            if (end >= 0)
                return end == used + count - 1 ? ParseRequest(buffer.AsMemory(0, end)) : null;
            used += count;
        }
        return null;
    }

    private static BridgeRequest? ParseRequest(ReadOnlyMemory<byte> message)
    {
        try
        {
            using var doc = JsonDocument.Parse(message, new JsonDocumentOptions { MaxDepth = 4 });
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object || ReadString(root, "method") is not { } method)
                return null;
            if (method == "get_state" && root.EnumerateObject().Count() == 1)
                return new BridgeRequest(method, null, null);
            if (method == "perform_action" && root.EnumerateObject().Count() == 3
                && ReadString(root, "state_id") is { Length: <= 128 } stateId
                && ReadString(root, "action_id") is { Length: <= 128 } actionId)
                return new BridgeRequest(method, stateId, actionId);
        }
        catch (JsonException)
        {
            // Malformed requests do not reach the game's UI thread.
        }
        return null;
    }

    private static string? ReadString(JsonElement root, string name) =>
        root.TryGetProperty(name, out var property) && property.ValueKind == JsonValueKind.String ? property.GetString() : null;
}
