"""Expose the live STS2 Steam mod over local MCP stdio."""

import ctypes
from ctypes import wintypes
import json
import math
import os
import re
import sys
from time import monotonic, sleep


PIPE_PATH = r"\\.\pipe\sts2-live-bridge-v1"
MAX_REQUEST = 8 * 1024
MAX_RESPONSE = 2 * 1024 * 1024
CHUNK_SIZE = 16 * 1024
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
ID_PATTERN = r"[!-~]{1,128}"
TOOLS = {
    "get_state": {
        "name": "get_state",
        "description": "Read the current Steam single-player game state and legal action IDs.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    "perform_action": {
        "name": "perform_action",
        "description": "Perform one legal action using the state ID and action ID returned by get_state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_id": {"type": "string", "pattern": f"^{ID_PATTERN}$"},
                "action_id": {"type": "string", "pattern": f"^{ID_PATTERN}$"},
            },
            "required": ["state_id", "action_id"],
            "additionalProperties": False,
        },
        "annotations": {"openWorldHint": False},
    },
}


class BridgeError(RuntimeError):
    """The local Steam mod rejected the request or could not be reached."""


def _encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _decode(data):
    def invalid_constant(value):
        raise ValueError(f"Invalid JSON number {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            return invalid_constant(value)
        return number

    return json.loads(data.decode("utf-8"), parse_constant=invalid_constant, parse_float=finite_float)


def _validate_args(method, args):
    if method == "get_state" and args == {}:
        return
    if method == "perform_action" and isinstance(args, dict) and args.keys() == {"state_id", "action_id"}:
        if all(isinstance(value, str) and re.fullmatch(ID_PATTERN, value) for value in args.values()):
            return
    raise ValueError("Supply only a valid state_id and action_id for perform_action, or no arguments for get_state.")


def _configure(dll, name, result, *arguments):
    fn = getattr(dll, name)
    fn.restype = result
    fn.argtypes = arguments
    return fn


class _WindowsPipe:
    """Use byte-mode nonblocking I/O so connect, writes, and reads share a deadline."""

    INVALID_HANDLE = ctypes.c_void_p(-1).value
    NO_DATA = 232
    PIPE_BUSY = 231
    PIPE_NOWAIT = 1
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    TOKEN_QUERY = 0x0008
    TOKEN_USER = 1

    def __init__(self):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        security = ctypes.WinDLL("advapi32", use_last_error=True)
        handle, dword, boolean = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
        pdword = ctypes.POINTER(dword)
        ptr = ctypes.c_void_p
        self.create_file = _configure(kernel, "CreateFileW", handle, wintypes.LPCWSTR, dword, dword,
                                      ptr, dword, dword, handle)
        self.close = _configure(kernel, "CloseHandle", boolean, handle)
        self.pipe_mode = _configure(kernel, "SetNamedPipeHandleState", boolean, handle, pdword, ptr, ptr)
        self.server_pid = _configure(kernel, "GetNamedPipeServerProcessId", boolean, handle, pdword)
        self.read = _configure(kernel, "ReadFile", boolean, handle, ptr, dword, pdword, ptr)
        self.write = _configure(kernel, "WriteFile", boolean, handle, ptr, dword, pdword, ptr)
        self.current_process = _configure(kernel, "GetCurrentProcess", handle)
        self.open_process = _configure(kernel, "OpenProcess", handle, dword, boolean, dword)
        self.open_token = _configure(security, "OpenProcessToken", boolean, handle, dword, ctypes.POINTER(handle))
        self.token_info = _configure(security, "GetTokenInformation", boolean, handle, dword, ptr, dword, pdword)
        self.equal_sid = _configure(security, "EqualSid", boolean, ptr, ptr)

    @staticmethod
    def pause(deadline):
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise BridgeError("The Steam mod did not respond before the local pipe deadline.")
        sleep(min(0.025, remaining))

    def connect(self, deadline):
        # Identification is sufficient for the mod's same-user check and cannot
        # be used by the server to impersonate the launcher process.
        generic_read_write = 0xC0000000
        open_existing = 3
        security_identification = 0x00110000
        recreate_deadline = min(deadline, monotonic() + 0.25)
        while monotonic() < deadline:
            pipe = self.create_file(PIPE_PATH, generic_read_write, 0, None,
                                    open_existing, security_identification, None)
            if pipe != self.INVALID_HANDLE:
                return pipe
            error = ctypes.get_last_error()
            if error == 2:
                # The mod briefly recreates its pipe between client requests.
                if monotonic() >= recreate_deadline:
                    raise BridgeError("The Steam mod bridge is unavailable. Launch the game with the live bridge mod enabled.")
            elif error != self.PIPE_BUSY:
                raise BridgeError(f"Could not open the local Steam mod pipe (Windows error {error}).")
            self.pause(deadline)
        raise BridgeError("The Steam mod pipe stayed busy until the deadline.")

    def user_token_data(self, process):
        token = wintypes.HANDLE()
        if not self.open_token(process, self.TOKEN_QUERY, ctypes.byref(token)):
            raise BridgeError("Could not verify the Steam mod process user.")
        try:
            size = wintypes.DWORD()
            self.token_info(token, self.TOKEN_USER, None, 0, ctypes.byref(size))
            if not 0 < size.value <= 4096:
                raise BridgeError("Could not read the Steam mod process user information.")
            data = ctypes.create_string_buffer(size.value)
            if not self.token_info(token, self.TOKEN_USER, data, size, ctypes.byref(size)):
                raise BridgeError("Could not read the Steam mod process user information.")
            return data
        finally:
            self.close(token)

    def verify_user(self, pipe):
        pid = wintypes.DWORD()
        if not self.server_pid(pipe, ctypes.byref(pid)) or not pid.value:
            raise BridgeError("Could not identify the process hosting the Steam mod pipe.")
        server = self.open_process(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not server:
            raise BridgeError("Could not verify the process hosting the Steam mod pipe.")
        try:
            local_user = self.user_token_data(self.current_process())
            server_user = self.user_token_data(server)
            local_sid = ctypes.c_void_p.from_buffer(local_user)
            server_sid = ctypes.c_void_p.from_buffer(server_user)
            if not self.equal_sid(local_sid, server_sid):
                raise BridgeError("The Steam mod pipe belongs to a different Windows user.")
        finally:
            self.close(server)

    def send(self, pipe, data, deadline):
        sent = wintypes.DWORD()
        offset = 0
        while offset < len(data):
            if monotonic() >= deadline:
                raise BridgeError("The Steam mod did not read the local pipe request before the deadline.")
            sent.value = 0
            chunk = data[offset:]
            ok = self.write(pipe, chunk, len(chunk), ctypes.byref(sent), None)
            if not ok and (error := ctypes.get_last_error()) != self.NO_DATA:
                raise BridgeError(f"Could not write to the local Steam mod pipe (Windows error {error}).")
            if sent.value == 0:
                self.pause(deadline)
            offset += sent.value

    def receive(self, pipe, deadline):
        frame = bytearray()
        buffer = ctypes.create_string_buffer(CHUNK_SIZE)
        size = wintypes.DWORD()
        while monotonic() < deadline:
            size.value = 0
            if not self.read(pipe, buffer, CHUNK_SIZE, ctypes.byref(size), None):
                error = ctypes.get_last_error()
                if error != self.NO_DATA:
                    raise BridgeError(f"The Steam mod closed or failed to read the local pipe (Windows error {error}).")
            if size.value == 0:
                self.pause(deadline)
                continue
            data = buffer.raw[:size.value]
            content, delimiter, trailing = data.partition(b"\n")
            if len(frame) + len(content) > MAX_RESPONSE:
                raise BridgeError("The Steam mod reply exceeded the local size limit.")
            frame.extend(content)
            if delimiter:
                if trailing:
                    raise BridgeError("The Steam mod sent an unexpected second response.")
                return frame
        raise BridgeError("The Steam mod did not finish its local pipe reply before the deadline.")

    def exchange(self, data, deadline):
        pipe = self.connect(deadline)
        try:
            self.verify_user(pipe)
            mode = wintypes.DWORD(self.PIPE_NOWAIT)
            if not self.pipe_mode(pipe, ctypes.byref(mode), None, None):
                raise BridgeError("Could not configure the local Steam mod pipe.")
            self.send(pipe, data, deadline)
            return self.receive(pipe, deadline)
        finally:
            self.close(pipe)


def call_bridge(method, *, timeout=8.0, **args):
    """Call one operation on the local game mod, returning its successful result."""
    _validate_args(method, args)
    if type(timeout) not in (int, float) or not 0 < timeout <= 60 or not math.isfinite(timeout):
        raise ValueError("The Steam mod pipe timeout must be greater than zero and at most 60 seconds.")
    if os.name != "nt":
        raise BridgeError("The live Steam mod pipe is only available on Windows.")
    request = _encode({"method": method, **args}) + b"\n"
    deadline = monotonic() + timeout
    data = _WindowsPipe().exchange(request, deadline)
    try:
        reply = _decode(data)
    except (ValueError, RecursionError) as error:
        raise BridgeError("The Steam mod returned invalid UTF-8 JSON.") from error
    if isinstance(reply, dict):
        if reply.get("ok") is True and "result" in reply:
            return reply["result"]
        if reply.get("ok") is False and isinstance(reply.get("error"), str):
            error = " ".join(reply["error"].split())[:500]
            raise BridgeError(error or "The Steam mod rejected the request.")
    raise BridgeError("The Steam mod returned an invalid response envelope.")


def _success(identifier, result):
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _error(identifier, code, message):
    return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}


class _McpSession:
    def __init__(self, call):
        self.protocol_version = None
        self.initialized = False
        self.call = call

    def dispatch(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "Invalid request")
        if "method" not in message and ("result" in message or "error" in message):
            return None
        method, identifier = message.get("method"), message.get("id")
        if not isinstance(method, str) or ("id" in message and type(identifier) not in (int, str)):
            return _error(None, -32600, "Invalid request")
        if "id" not in message:
            if method == "notifications/initialized" and self.protocol_version is not None:
                self.initialized = True
            return None
        params = message.get("params", {})
        if not isinstance(params, dict):
            return _error(identifier, -32602, "Invalid parameters")
        if method == "ping":
            return _success(identifier, {})
        if method == "initialize":
            return self.initialize(identifier, params)
        if not self.initialized:
            return _error(identifier, -32002, "The MCP session is not initialized")
        if method == "tools/list":
            if params.get("cursor") is not None:
                return _error(identifier, -32602, "No pagination cursor is available")
            return _success(identifier, {"tools": list(TOOLS.values())})
        if method == "tools/call":
            return self.call_tool(identifier, params)
        return _error(identifier, -32601, "Method not found")

    def initialize(self, identifier, params):
        version = params.get("protocolVersion")
        if self.protocol_version is not None or not isinstance(version, str):
            return _error(identifier, -32602, "Supply a protocol version when initializing a new MCP session")
        self.protocol_version = version if version in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return _success(identifier, {
            "protocolVersion": self.protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "sts2-live-bridge", "version": "1.0.0"},
        })

    def call_tool(self, identifier, params):
        method, arguments = params.get("name"), params.get("arguments", {})
        if not isinstance(method, str) or method not in TOOLS:
            return _error(identifier, -32602, "Unknown tool")
        try:
            _validate_args(method, arguments)
        except ValueError as error:
            return _error(identifier, -32602, str(error))
        try:
            value = self.call(method, **arguments)
            result = {"content": [{"type": "text", "text": _encode(value).decode("utf-8")}]}
            if self.protocol_version in PROTOCOL_VERSIONS[:2]:
                result["structuredContent"] = value if isinstance(value, dict) else {"result": value}
        except BridgeError as error:
            result = {"isError": True, "content": [{"type": "text", "text": str(error)}]}
        except (ValueError, RecursionError):
            result = {"isError": True, "content": [{"type": "text", "text": "The Steam mod returned an invalid tool result."}]}
        return _success(identifier, result)


def serve(source, destination, call=call_bridge):
    """Read UTF-8 JSON-RPC messages, writing only newline-delimited MCP replies."""
    session = _McpSession(call)
    while line := source.readline(MAX_REQUEST + 1):
        too_long = len(line) > MAX_REQUEST
        if too_long:
            reply = _error(None, -32700, "MCP request exceeds the line size limit")
        else:
            try:
                message = _decode(line)
            except (ValueError, RecursionError):
                reply = _error(None, -32700, "Invalid UTF-8 JSON")
            else:
                reply = session.dispatch(message)
        if reply is not None:
            try:
                serialized = _encode(reply)
            except (ValueError, RecursionError):
                serialized = _encode(_error(None, -32603, "The MCP reply could not be serialized"))
            destination.write(serialized + b"\n")
            destination.flush()
        if too_long and not line.endswith(b"\n"):
            break


if __name__ == "__main__":
    serve(sys.stdin.buffer, sys.stdout.buffer)
