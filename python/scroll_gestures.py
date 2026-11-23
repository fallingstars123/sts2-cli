"""Scoped Tk vertical scrolling for wheels, precise touchpads, and pointer drags."""

from dataclasses import dataclass
import sys
import tkinter as tk


_CLICK_CONTROLS = {
    "Button", "TButton", "Checkbutton", "TCheckbutton", "Radiobutton", "TRadiobutton",
    "Entry", "TEntry", "TCombobox", "Menubutton", "TMenubutton", "Scale", "TScale", "Spinbox", "TSpinbox",
    "Scrollbar", "TScrollbar",
}
_MODIFIERS = 0x2000D  # Shift, Control, and the X11/Windows Alt indicators.


def _promoted_touch():
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        extra = ctypes.windll.user32.GetMessageExtraInfo
        extra.argtypes = ()
        extra.restype = ctypes.c_size_t
        # The message's low bitfield distinguishes promoted touch from pen.
        return extra() & 0xFFFFFF80 == 0xFF515780
    except (AttributeError, OSError):
        return False


@dataclass
class _Contact:
    press: object
    last_y: int
    deferred: bool
    dragging: bool = False


class ScrollGestures:
    """Attach vertical gestures to one widget or the current widgets in a subtree.

    ``target`` is an optional outer view. ``resolver(widget)`` can pick the inner
    view instead of looking for one amongst the event widget's parents. A normal
    short press/release is still a click. Treeview presses are held until a tap
    or a horizontal gesture is recognized, so panning does not select a row.
    Use ``touch_only=True`` where mouse dragging must retain its own meaning.
    """

    def __init__(self, scope, *, target=None, descendants=False, resolver=None, drag=True, wheel=True,
                 defer_press=None, threshold=8, touch_only=False):
        self.scope = scope
        self.target = target
        self.resolver = resolver
        self.defer_press = defer_press
        self.threshold = max(1, int(threshold))
        self.touch_only = touch_only
        self.contact = None
        self.replaying = False
        self.remainders = {}
        self.widgets = set()
        self.bindings = {}
        self.tag = f"Sts2ScrollGestures:{id(self)}"
        self._bind("<Destroy>", self._destroy)
        if drag:
            self._bind("<ButtonPress-1>", self._press)
            self._bind("<B1-Motion>", self._motion)
            self._bind("<B1-Leave>", self._leave)
            self._bind("<ButtonRelease-1>", self._release)
        if wheel:
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self._bind(sequence, self._wheel)
            if tk.TkVersion >= 9.0:
                self._bind("<TouchpadScroll>", self._touchpad)
        self.add(scope, descendants=descendants)

    def _bind(self, sequence, callback):
        self.bindings[sequence] = self.scope.bind_class(self.tag, sequence, callback)

    def add(self, widget, *, descendants=False):
        """Include an additional widget and optionally its existing children."""
        if widget not in self.widgets:
            widget.bindtags((self.tag, *widget.bindtags()))
            self.widgets.add(widget)
        if descendants:
            for child in widget.winfo_children():
                self.add(child, descendants=True)

    def detach(self):
        """Remove this helper without altering another widget binding."""
        for widget in self.widgets:
            try:
                widget.bindtags(tuple(tag for tag in widget.bindtags() if tag != self.tag))
            except tk.TclError:
                pass
        for sequence, command in self.bindings.items():
            try:
                self.scope.unbind_class(self.tag, sequence)
                if command:
                    self.scope._root().deletecommand(command)
            except tk.TclError:
                pass
        self.widgets.clear()
        self.bindings.clear()
        self.remainders.clear()
        self.contact = None

    def _destroy(self, event):
        if event.widget is self.scope:
            self.detach()
        else:
            self.widgets.discard(event.widget)
            self.remainders.pop(event.widget, None)
            if self.contact is not None and self.contact.press.widget is event.widget:
                self.contact = None

    def _views(self, source):
        candidates = []
        if self.resolver is not None:
            candidates.append(self.resolver(source))
        else:
            parent = source
            while parent is not None:
                if parent in self.widgets and callable(getattr(parent, "yview", None)):
                    candidates.append(parent)
                if parent is self.scope:
                    break
                parent = getattr(parent, "master", None)
        if self.target is not None and self.target not in candidates:
            candidates.append(self.target)
        return (view for view in candidates if view is not None and callable(getattr(view, "yview", None)))

    @staticmethod
    def _range(view):
        try:
            first, last = view.yview()
            return float(first), float(last)
        except (TypeError, ValueError, tk.TclError):
            return 0.0, 1.0

    def _press(self, event):
        if self.replaying:
            return None
        self.contact = None
        if event.state & _MODIFIERS or (self.touch_only and not _promoted_touch()):
            return None
        widget = event.widget
        kind = widget.winfo_class()
        if kind in _CLICK_CONTROLS or (kind == "Treeview" and widget.identify_region(event.x, event.y) in {"heading", "separator"}):
            return None
        if not any(first > 0 or last < 1 for first, last in map(self._range, self._views(widget))):
            return None
        defer = self.defer_press
        if callable(defer):
            defer = defer(widget)
        if defer is None:
            defer = kind == "Treeview" or self.touch_only
        self.contact = _Contact(event, event.y_root, defer)
        return "break" if defer else None

    def _motion(self, event):
        contact = self.contact
        if contact is None or contact.press.widget is not event.widget:
            return None
        vertical = abs(event.y_root - contact.press.y_root)
        horizontal = abs(event.x_root - contact.press.x_root)
        if not contact.dragging:
            if max(vertical, horizontal) < self.threshold:
                return "break"
            if horizontal >= vertical:
                self.contact = None
                self._replay_press(contact)
                return None
            contact.dragging = True
        self._scroll(event.widget, contact.last_y - event.y_root)
        contact.last_y = event.y_root
        return "break"

    def _leave(self, event):
        if self.contact is not None and self.contact.press.widget is event.widget:
            return "break"
        return None

    def _release(self, event):
        contact, self.contact = self.contact, None
        if contact is None or contact.press.widget is not event.widget:
            return None
        vertical = abs(event.y_root - contact.press.y_root)
        horizontal = abs(event.x_root - contact.press.x_root)
        if contact.dragging or (vertical >= self.threshold and vertical > horizontal):
            self._scroll(event.widget, contact.last_y - event.y_root)
            return "break"
        self._replay_press(contact)
        return None

    def _replay_press(self, contact):
        if not contact.deferred:
            return
        event = contact.press
        self.replaying = True
        try:
            # The real press is already in Tk's event history. A different timestamp
            # prevents a replayed single tap from turning into a synthetic double-click.
            replay_time = (event.time + 10_000) & 0x7FFFFFFF
            event.widget.event_generate("<ButtonPress-1>", x=event.x, y=event.y, rootx=event.x_root,
                                        rooty=event.y_root, state=event.state, time=replay_time, when="now")
        except tk.TclError:
            pass
        finally:
            self.replaying = False

    def _wheel(self, event):
        if event.state & 0x0001:
            return None  # Preserve widget-specific Shift-wheel bindings.
        delta = event.delta
        pixels = -delta / 2 if delta else -60 if event.num == 4 else 60 if event.num == 5 else 0
        return "break" if self._scroll(event.widget, pixels) else None

    def _touchpad(self, event):
        try:
            _, dy = event.widget.tk.splitlist(event.widget.tk.call("tk::PreciseScrollDeltas", event.delta))
            pixels = float(event.widget.tk.call("tk::ScaleNum", -float(dy)))
        except (TypeError, ValueError, tk.TclError):
            return None
        return "break" if self._scroll(event.widget, pixels) else None

    @staticmethod
    def _unit_height(view, kind):
        if kind == "Treeview":
            row = view.identify_row(view.winfo_height() // 2)
            bounds = view.bbox(row) if row else ()
            if bounds and bounds[3] > 0:
                return bounds[3]
            return 22
        if kind == "Text":
            return max(1, int(view.tk.call("font", "metrics", view.cget("font"), "-linespace")))
        return 18

    def _scroll(self, source, pixels):
        if not pixels:
            return False
        for view in self._views(source):
            top, bottom = self._range(view)
            if (pixels < 0 and top <= 0) or (pixels > 0 and bottom >= 1):
                self.remainders.pop(view, None)
                continue
            try:
                kind = view.winfo_class()
                if kind == "Canvas":
                    visible = max(1, view.winfo_height() - 2 * (
                        view.winfo_pixels(view.cget("borderwidth")) + view.winfo_pixels(view.cget("highlightthickness"))))
                    view.yview_moveto(max(0, min(1, top + pixels * (bottom - top) / visible)))
                else:
                    precise = kind == "Text" and tk.TkVersion >= 9.0
                    unit = 1 if precise else self._unit_height(view, kind)
                    distance = self.remainders.get(view, 0) + pixels
                    lines = int(distance / unit)
                    self.remainders[view] = distance - lines * unit
                    if lines:
                        view.yview_scroll(lines, "pixels" if precise else "units")
                return True
            except (TypeError, ValueError, tk.TclError):
                self.remainders.pop(view, None)
        return False
