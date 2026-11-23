"""Observe and operate only the foreground Slay the Spire 2 game client."""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
from threading import Condition
import time
from contextlib import contextmanager


GAME_EXE = "SlayTheSpire2.exe"
KEYS = {
    "enter": 0x0D, "space": 0x20, "tab": 0x09, "escape": 0x1B,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "e": 0x45,
    **{str(digit): 0x30 + digit for digit in range(10)},
}
MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt, and Windows.
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x01
KEYEVENTF_KEYUP = 0x02
KEYEVENTF_SCANCODE = 0x08
MAPVK_VK_TO_VSC_EX = 4
GW_HWNDPREV = 3
GWL_EXSTYLE = -20
PASSIVE_LAYERED_WINDOW = 0x08000000 | 0x00080000 | 0x00000020  # No-activate, layered, transparent.
DWMWA_CLOAKED = 14
DWMWA_EXTENDED_FRAME_BOUNDS = 9
DPI_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
MIN_KEY_INTERVAL = 0.15
MIN_CLIENT_SIZE = (400, 225)
MAX_CLIENT_SIZE = 8192
GRAPHICS_FRAME_TIMEOUT = 3.0


class SteamWindowError(RuntimeError):
    """The game window cannot be safely observed or controlled."""


class _KeyboardInput(ctypes.Structure):
    _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("extra", ctypes.c_size_t)]


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("data", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class _InputFields(ctypes.Union):
    # SendInput expects the full Win32 INPUT union, including its mouse alignment.
    _fields_ = [("keyboard", _KeyboardInput), ("mouse", _MouseInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("fields",)
    _fields_ = [("type", wintypes.DWORD), ("fields", _InputFields)]


def _api(dll, name, result, *arguments):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = arguments
    return function


def _exe_path(path):
    return os.path.normcase(os.path.realpath(path))


def _rectangle(bounds):
    return bounds.left, bounds.top, bounds.right, bounds.bottom


def _size(bounds):
    left, top, right, bottom = bounds
    return right - left, bottom - top


def _graphics_client(frame, geometry):
    client, window_frames = geometry
    if _size(client) == frame.size:
        return frame
    left, top, right, bottom = client
    candidates = {
        (left - x, top - y, right - x, bottom - y)
        for x, y, end_x, end_y in window_frames
        if frame.size == (end_x - x, end_y - y) and x <= left <= right <= end_x and y <= top <= bottom <= end_y
    }
    if len(candidates) != 1:
        raise SteamWindowError("Windows Graphics Capture could not identify the game client within the frame.")
    return frame.crop(candidates.pop())


def _blank(frame):
    channels = frame.resize((32, 18)).getextrema()[:3]
    return max(high for _, high in channels) <= 12 or max(high - low for low, high in channels) <= 4


class _GraphicsCapture:
    """One target-window capture session, with frames copied only while requested."""

    def __init__(self, hwnd):
        from PIL import Image

        try:
            from windows_capture import WindowsCapture
        except ImportError as error:
            raise SteamWindowError("Windows Graphics Capture is unavailable in this launcher environment.") from error

        self._ready = Condition()
        self._requested = True
        self._closed = False
        self._frame = None
        self._timestamp = None
        self._failed = False
        try:
            # The only target is the verified HWND; system border and secondary-window defaults stay in effect.
            capture = WindowsCapture(window_hwnd=hwnd, cursor_capture=False)

            @capture.event
            def on_frame_arrived(frame, _control):
                with self._ready:
                    if (not self._requested or self._closed
                            or self._timestamp is not None and frame.timespan <= self._timestamp):
                        return
                    self._requested = False
                    try:
                        size = frame.width, frame.height
                        if not all(0 < dimension <= MAX_CLIENT_SIZE for dimension in size):
                            raise ValueError("Unexpected graphics frame size")
                        pixels = frame.frame_buffer.tobytes()
                        self._frame = Image.frombytes("RGB", size, pixels, "raw", "BGRX")
                        self._timestamp = frame.timespan
                    except (AttributeError, TypeError, ValueError):
                        self._failed = True
                    self._ready.notify_all()

            @capture.event
            def on_closed():
                with self._ready:
                    self._closed = True
                    self._frame = None
                    self._ready.notify_all()

            self._capture = capture
            self._control = capture.start_free_threaded()
        except Exception as error:
            raise SteamWindowError("Windows Graphics Capture could not start for the Steam game window.") from error

    def read(self):
        with self._ready:
            self._requested = self._frame is None
            self._ready.wait_for(lambda: self._frame is not None or self._closed or self._failed,
                                 timeout=GRAPHICS_FRAME_TIMEOUT)
            self._requested = False
            if self._closed:
                raise SteamWindowError("Windows Graphics Capture closed the Steam game window stream.")
            if self._failed:
                raise SteamWindowError("Windows Graphics Capture returned an unreadable game frame.")
            frame, self._frame = self._frame, None
            if frame is None:
                raise SteamWindowError("Windows Graphics Capture timed out waiting for a fresh game frame.")
            return frame

    def close(self):
        with self._ready:
            self._closed = True
            self._frame = None
            self._requested = False
            self._ready.notify_all()
        control, self._control = self._control, None
        if control is not None:
            try:
                control.stop()
            except Exception:
                # The native session may already have ended after reporting an error.
                pass


class _Windows:
    def __init__(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        hwnd = wintypes.HWND
        dword = wintypes.DWORD
        handle = wintypes.HANDLE
        integer = wintypes.BOOL
        self.enum_callback = ctypes.WINFUNCTYPE(integer, hwnd, wintypes.LPARAM)
        self.enum_windows = _api(user32, "EnumWindows", integer, self.enum_callback, wintypes.LPARAM)
        self.foreground = _api(user32, "GetForegroundWindow", hwnd)
        self.visible = _api(user32, "IsWindowVisible", integer, hwnd)
        self.iconic = _api(user32, "IsIconic", integer, hwnd)
        self.window_pid = _api(user32, "GetWindowThreadProcessId", dword, hwnd, ctypes.POINTER(dword))
        self.client_rect = _api(user32, "GetClientRect", integer, hwnd, ctypes.POINTER(wintypes.RECT))
        self.client_to_screen = _api(user32, "ClientToScreen", integer, hwnd, ctypes.POINTER(wintypes.POINT))
        self.window_rect = _api(user32, "GetWindowRect", integer, hwnd, ctypes.POINTER(wintypes.RECT))
        self.window_style = _api(user32, "GetWindowLongW", wintypes.LONG, hwnd, ctypes.c_int)
        self.neighbor = _api(user32, "GetWindow", hwnd, hwnd, wintypes.UINT)
        self.window_dpi = _api(user32, "GetWindowDpiAwarenessContext", ctypes.c_void_p, hwnd)
        self.thread_dpi = _api(user32, "SetThreadDpiAwarenessContext", ctypes.c_void_p, ctypes.c_void_p)
        self.key_state = _api(user32, "GetAsyncKeyState", ctypes.c_short, ctypes.c_int)
        self.scan_code = _api(user32, "MapVirtualKeyW", wintypes.UINT, wintypes.UINT, wintypes.UINT)
        self.send_input = _api(user32, "SendInput", wintypes.UINT, wintypes.UINT,
                               ctypes.POINTER(_Input), ctypes.c_int)
        self.open_process = _api(kernel32, "OpenProcess", handle, dword, integer, dword)
        self.image_name = _api(kernel32, "QueryFullProcessImageNameW", integer, handle, dword,
                               wintypes.LPWSTR, ctypes.POINTER(dword))
        self.close_handle = _api(kernel32, "CloseHandle", integer, handle)
        self.dwm_attribute = _api(dwmapi, "DwmGetWindowAttribute", ctypes.c_long,
                                  hwnd, dword, ctypes.c_void_p, dword)

    def pid_of(self, hwnd):
        pid = wintypes.DWORD()
        self.window_pid(hwnd, ctypes.byref(pid))
        return pid.value

    def path_of(self, pid):
        process = self.open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not process:
            return None
        try:
            path = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(path))
            if self.image_name(process, 0, path, ctypes.byref(length)):
                return _exe_path(path.value)
            return None
        finally:
            self.close_handle(process)

    @contextmanager
    def dpi(self, context):
        previous = self.thread_dpi(context) if context else None
        if not previous:
            raise SteamWindowError("Windows did not report the Steam game window's DPI.")
        try:
            yield
        finally:
            self.thread_dpi(previous)

    def client_size(self, hwnd):
        # Pillow's window capture queries GetClientRect in the target window's DPI context.
        with self.dpi(self.window_dpi(hwnd)):
            bounds = wintypes.RECT()
            if not self.client_rect(hwnd, ctypes.byref(bounds)):
                raise SteamWindowError("The Steam game client size could not be read.")
            return bounds.right - bounds.left, bounds.bottom - bounds.top

    def graphics_geometry(self, hwnd):
        """Return physical client bounds and possible origins of a WGC window frame."""
        with self.dpi(DPI_PER_MONITOR_AWARE_V2):
            client = wintypes.RECT()
            if not self.client_rect(hwnd, ctypes.byref(client)):
                raise SteamWindowError("The Steam game client bounds could not be read.")
            top_left = wintypes.POINT(client.left, client.top)
            bottom_right = wintypes.POINT(client.right, client.bottom)
            if not (self.client_to_screen(hwnd, ctypes.byref(top_left))
                    and self.client_to_screen(hwnd, ctypes.byref(bottom_right))):
                raise SteamWindowError("The Steam game client bounds could not be positioned.")
            inner = top_left.x, top_left.y, bottom_right.x, bottom_right.y
            bounds = wintypes.RECT()
            frames = []
            if self.window_rect(hwnd, ctypes.byref(bounds)):
                frames.append(_rectangle(bounds))
            if not self.dwm_attribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(bounds), ctypes.sizeof(bounds)):
                frames.append(_rectangle(bounds))
            return inner, tuple(frames)

    def is_unobstructed(self, hwnd):
        with self.dpi(DPI_PER_MONITOR_AWARE_V2):
            bounds = wintypes.RECT()
            if not self.client_rect(hwnd, ctypes.byref(bounds)):
                return False
            top_left = wintypes.POINT(bounds.left, bounds.top)
            bottom_right = wintypes.POINT(bounds.right, bounds.bottom)
            if not (self.client_to_screen(hwnd, ctypes.byref(top_left))
                    and self.client_to_screen(hwnd, ctypes.byref(bottom_right))):
                return False
            tested = {hwnd}
            above = self.neighbor(hwnd, GW_HWNDPREV)
            while above and above not in tested:
                tested.add(above)
                if self.visible(above) and not self.iconic(above):
                    # Transparent, non-activating layered overlays do not take game focus.
                    # Pillow captures the game client without CAPTUREBLT, which excludes their pixels.
                    style = self.window_style(above, GWL_EXSTYLE)
                    if style & PASSIVE_LAYERED_WINDOW == PASSIVE_LAYERED_WINDOW:
                        above = self.neighbor(above, GW_HWNDPREV)
                        continue
                    cloaked = wintypes.DWORD()
                    result = self.dwm_attribute(above, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
                    if result or not cloaked.value:
                        other = wintypes.RECT()
                        if not self.window_rect(above, ctypes.byref(other)):
                            return False
                        if (other.left < bottom_right.x and other.right > top_left.x
                                and other.top < bottom_right.y and other.bottom > top_left.y):
                            return False
                above = self.neighbor(above, GW_HWNDPREV)
            return not above


class SteamWindow:
    """One verified game window. Never brings any window to the foreground."""

    def __init__(self, native, hwnd, pid, expected_exe):
        self._native = native
        self.hwnd = hwnd
        self._pid = pid
        self._expected_exe = expected_exe
        self._last_key = None
        self._graphics = None

    @classmethod
    def find(cls, game_root):
        """Return a visible game window under the specified Steam installation, or None."""
        if sys.platform != "win32" or game_root is None:
            return None
        game_exe = Path(game_root) / GAME_EXE
        if not game_exe.is_file():
            return None
        expected = _exe_path(game_exe)
        if Path(expected).name.casefold() != GAME_EXE.casefold():
            return None
        native = _Windows()
        windows = []

        @native.enum_callback
        def visit(hwnd, _):
            if native.visible(hwnd):
                pid = native.pid_of(hwnd)
                if pid and native.path_of(pid) == expected:
                    windows.append(cls(native, hwnd, pid, expected))
            return True

        native.enum_windows(visit, 0)
        foreground = native.foreground()
        return next((window for window in windows if window.hwnd == foreground), windows[0] if windows else None)

    def is_foreground(self):
        native = self._native
        return (native.foreground() == self.hwnd and native.visible(self.hwnd) and not native.iconic(self.hwnd)
                and native.pid_of(self.hwnd) == self._pid and native.path_of(self._pid) == self._expected_exe)

    def _require_foreground(self):
        if not self.is_foreground():
            raise SteamWindowError("Bring the Slay the Spire 2 game window to the foreground.")

    def capture(self):
        """Return only the game client pixels. Never falls back to a desktop image."""
        from PIL import ImageGrab

        native = self._native
        try:
            self._require_foreground()
            size = native.client_size(self.hwnd)
            if any(not minimum <= dimension <= MAX_CLIENT_SIZE for minimum, dimension in zip(MIN_CLIENT_SIZE, size)):
                raise SteamWindowError("The game client is too small to read or exceeds the capture size limit.")
            if not native.is_unobstructed(self.hwnd):
                raise SteamWindowError("Dismiss windows or desktop overlays covering the Steam game.")
            self._require_foreground()
            if self._graphics is None:
                try:
                    frame = ImageGrab.grab(window=self.hwnd, include_layered_windows=False)
                except (TypeError, OSError):
                    frame = None
                self._require_foreground()
                if (native.client_size(self.hwnd) != size or not native.is_unobstructed(self.hwnd)
                        or (frame is not None and frame.size != size)):
                    raise SteamWindowError("The Steam game window changed during capture.")
                if frame is not None and not _blank(frame):
                    return frame

            geometry = native.graphics_geometry(self.hwnd)
            self._require_foreground()
            if self._graphics is None:
                self._graphics = _GraphicsCapture(self.hwnd)
            frame = self._graphics.read()
            self._require_foreground()
            if native.graphics_geometry(self.hwnd) != geometry or not native.is_unobstructed(self.hwnd):
                raise SteamWindowError("The Steam game window changed during graphics capture.")
            frame = _graphics_client(frame, geometry)
            if _blank(frame):
                raise SteamWindowError("The Steam game capture was blank. Try windowed or borderless mode.")
            return frame
        except SteamWindowError:
            self.close()
            raise

    def close(self):
        """End the native graphics capture session if it was needed."""
        capture, self._graphics = self._graphics, None
        if capture is not None:
            capture.close()

    def press(self, key):
        """Tap one allowed game key, with a fresh foreground check for each tap."""
        if not isinstance(key, str) or key not in KEYS:
            raise SteamWindowError("The requested key is outside the Steam game controls.")
        now = time.monotonic()
        if self._last_key is not None and now - self._last_key < MIN_KEY_INTERVAL:
            raise SteamWindowError("Wait for the Steam game to respond before pressing another key.")

        native = self._native
        virtual_key = KEYS[key]
        scan = native.scan_code(virtual_key, MAPVK_VK_TO_VSC_EX)
        if not scan:
            raise SteamWindowError("Windows could not map the requested game key.")
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if scan >> 8 == 0xE0 else 0)
        tap = (_Input * 2)()
        tap[0].type = tap[1].type = INPUT_KEYBOARD
        tap[0].keyboard = _KeyboardInput(0, scan & 0xFF, flags, 0, 0)
        tap[1].keyboard = _KeyboardInput(0, scan & 0xFF, flags | KEYEVENTF_KEYUP, 0, 0)

        self._require_foreground()
        if not native.is_unobstructed(self.hwnd):
            raise SteamWindowError("Dismiss windows or desktop overlays covering the Steam game.")
        if any(native.key_state(held) & 0x8000 for held in (*MODIFIERS, virtual_key)):
            raise SteamWindowError("Release the keyboard before letting the AI send a game key.")
        self._require_foreground()
        sent = native.send_input(2, tap, ctypes.sizeof(_Input))
        self._last_key = now
        if sent != 2:
            if sent == 1 and self.is_foreground():
                native.send_input(1, ctypes.byref(tap[1]), ctypes.sizeof(_Input))
            raise SteamWindowError("Windows did not accept the complete game key press.")
