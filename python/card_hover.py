"""Show inventory item details without taking focus from the list."""

import tkinter as tk
from tkinter import font


class CardHover:
    """Resolve inventory rows or slots to display text and an optional Tk image."""

    def __init__(self, tree, resolve, *, background, foreground, muted, border, delay=360,
                 hit_test=None, bounds=None, protected=None, near_pointer=False):
        self.tree = tree
        self.resolve = resolve
        self.hit_test = hit_test or (lambda _x, y: tree.identify_row(y))
        self.bounds = bounds or self.row_bounds
        self.anchor_to_slot = bounds is not None
        self.near_pointer = near_pointer
        self.protected = protected
        self.background = background
        self.foreground = foreground
        self.muted = muted
        self.border = border
        self.delay = delay
        self.row = None
        self.job = None
        self.popup = None
        self.rules_view = None
        self.point = (0, 0)
        self.anchor = None
        self.body_font = font.nametofont("TkDefaultFont", root=tree).copy()
        self.heading_font = self.body_font.copy()
        size = self.body_font["size"]
        self.heading_font.configure(size=size + (1 if size >= 0 else -1), weight="bold")
        self.default_family = self.body_font.actual("family")
        families = {name.casefold(): name for name in font.families(root=tree)}
        self.han_family = families.get("microsoft yahei ui") or families.get("microsoft yahei")

        tree.bind("<Motion>", self.move, add="+")
        tree.bind("<Shift-MouseWheel>", self.scroll_rules, add="+")
        tree.bind("<KeyPress>", self.key_pressed, add="+")
        for event in ("<Leave>", "<Unmap>", "<Destroy>", "<MouseWheel>", "<ButtonPress>"):
            tree.bind(event, self.hide, add="+")
        try:
            tree.bind("<TouchpadScroll>", self.hide, add="+")
        except tk.TclError:
            pass  # Tk 8.6 reports touchpad gestures as mouse wheel events.

    def hide(self, _event=None):
        """Cancel the pending preview before refreshing the list."""
        if self.job is not None:
            self.tree.after_cancel(self.job)
            self.job = None
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None
        self.row = None
        self.anchor = None
        self.rules_view = None

    def key_pressed(self, event):
        if self.rules_view is None or event.keysym not in ("Shift_L", "Shift_R"):
            self.hide()

    def scroll_rules(self, event):
        if self.rules_view is None:
            self.hide()
            return None
        direction = -1 if event.delta > 0 else 1
        self.rules_view.yview_scroll(direction * max(1, abs(event.delta) // 120), "units")
        return "break"

    def move(self, event):
        self.point = (event.x_root, event.y_root)
        row = self.hit_test(event.x, event.y)
        if row == self.row:
            return
        self.hide()
        if row is not None and row != "":
            self.row = row
            self.anchor = self.viewport()
            self.job = self.tree.after(self.delay, self.show)

    def viewport(self):
        return (self.tree.winfo_rootx(), self.tree.winfo_rooty(),
                self.tree.winfo_width(), self.tree.winfo_height(), self.tree.yview())

    def row_bounds(self, row):
        return self.tree.bbox(row) if self.tree.exists(row) else None

    def row_is_visible(self):
        return (self.row is not None and self.tree.winfo_ismapped()
                and self.bounds(self.row) and self.viewport() == self.anchor)

    def show(self):
        self.job = None
        details = self.resolve(self.row) if self.row_is_visible() else None
        if not details or not details.get("name"):
            self.hide()
            return

        self.configure_fonts(details)
        self.popup = popup = tk.Toplevel(self.tree)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self.tree.winfo_toplevel())
        card = bool(details.get("card"))
        metadata = " · ".join(str(details[key]) for key in ("type", "rarity") if details.get(key))
        reference = details.get("render")
        if card and self.has_photo(reference):
            self.render_reference(popup, reference)
        elif card:
            self.render_card(popup, details, metadata)
        else:
            self.render_details(popup, details, metadata)

        popup.update_idletasks()
        if self.popup is not popup:
            return
        if not self.row_is_visible():
            self.hide()
            return
        width, height = popup.winfo_reqwidth(), popup.winfo_reqheight()
        width = min(width, self.tree.winfo_vrootwidth())
        height = min(height, self.tree.winfo_vrootheight())
        place = self.position(width, height)
        if place is None:
            self.hide()
            return
        popup.geometry(f"{width}x{height}{place}")
        popup.deiconify()
        popup.lift()
        self.job = self.tree.after(80, self.watch_viewport)

    def configure_fonts(self, details):
        language = details.get("language")
        if isinstance(language, str) and language:
            chinese = language.casefold().startswith("zh")
        else:
            sample = f"{details['name']} {details.get('description') or ''}"
            chinese = (any("\u3400" <= char <= "\u9fff" for char in sample)
                       and not any("\u3040" <= char <= "\u30ff" or "\uac00" <= char <= "\ud7af" for char in sample))
        family = self.han_family if chinese and self.han_family else self.default_family
        self.body_font.configure(family=family)
        self.heading_font.configure(family=family)

    @staticmethod
    def has_photo(photo):
        return bool(photo and photo.width() and photo.height())

    def card_canvas(self, popup):
        background = self.background
        if popup.tk.call("tk", "windowingsystem") == "win32":
            try:
                popup.wm_attributes("-transparentcolor", "#010203")
            except tk.TclError:
                pass
            else:
                background = "#010203"
                popup.configure(background=background)
        return tk.Canvas(popup, background=background, borderwidth=0, highlightthickness=0)

    def render_reference(self, popup, reference):
        canvas = self.card_canvas(popup)
        canvas.pack(fill="both", expand=True)
        ratio = reference.width() / reference.height()
        width = max(1, min(reference.width(), self.tree.winfo_vrootwidth(),
                           int(self.tree.winfo_vrootheight() * ratio)))
        while True:
            height = max(1, round(width / ratio))
            if width <= 104 or self.position(width, height) is not None:
                break
            width = max(104, width - 18)

        canvas.configure(width=width, height=height)
        photo = self.resize_photo(reference, width, height)
        canvas.images = [photo]
        canvas.create_image(0, 0, image=photo, anchor="nw", tags="render")

    def render_details(self, popup, details, metadata):
        panel = tk.Frame(popup, background=self.background, highlightbackground=self.border, highlightthickness=1)
        panel.pack(fill="both", expand=True)
        image = details.get("image")
        has_image = self.has_photo(image)
        if has_image:
            scale = min(1, 58 / max(image.width(), image.height()))
            art = self.resize_photo(image, max(1, round(image.width() * scale)), max(1, round(image.height() * scale)))
            self.portrait(panel, art).pack(side="left", anchor="n", padx=(10, 8), pady=9)
        column = tk.Frame(panel, background=self.background)
        column.pack(side="left", fill="both", expand=True, padx=(0 if has_image else 10, 10), pady=8)
        header = tk.Frame(column, background=self.background)
        header.pack(fill="x")
        cost = details.get("cost")
        if cost is not None and cost != "":
            tk.Label(header, text=cost, foreground=self.foreground, background=self.border, padx=6).pack(side="right")
        tk.Label(header, text=details["name"], foreground=self.foreground, background=self.background,
                 font=self.heading_font, justify="left", wraplength=208).pack(side="left")

        description = details.get("description")
        for value, color in ((metadata, self.muted), (description, self.foreground)):
            if value:
                tk.Label(column, text=value, font=self.body_font, foreground=color, background=self.background,
                         justify="left", wraplength=242, anchor="w").pack(fill="x", pady=(5, 0))

    def render_card(self, popup, details, metadata):
        canvas = self.card_canvas(popup)
        canvas.pack(fill="both", expand=True)
        canvas.images = []
        frame = details.get("frame")
        accent = details.get("accent") or self.border
        natural_width, natural_height = (frame.width(), frame.height()) if frame else (228, 322)
        ratio = natural_width / natural_height
        limit = int(min(512, self.tree.winfo_vrootwidth() - 18, (self.tree.winfo_vrootheight() - 18) * ratio))
        width = min(natural_width, limit)
        while width > 145 and self.position(width, round(width / ratio)) is None:
            width -= 18

        description = details.get("description") or ""
        cost = details.get("cost")
        has_cost = cost is not None and cost != ""
        title_font = self.heading_font.copy()
        canvas.title_font = title_font
        canvas.create_text(0, 0, text=details["name"], font=title_font, fill=self.foreground, anchor="w", tags="title")
        canvas.create_text(0, 0, text=metadata, font=self.body_font, fill=self.muted, anchor="nw", tags="metadata")
        canvas.create_text(0, 0, text=description, font=self.body_font, fill=self.foreground, anchor="nw", tags="rules")

        while True:
            height = round(width / ratio)
            left, right = round(width * .15), round(width * .85)
            head_y = round(height * .060)
            title_x = left + (31 if has_cost else 0)
            canvas.coords("title", title_x, head_y)
            canvas.itemconfigure("title", width=max(1, right - title_x))
            canvas.coords("metadata", left, round(height * .610))
            canvas.itemconfigure("metadata", width=right - left)
            rules_y = canvas.bbox("metadata")[3] + 7 if metadata else round(height * .615)
            rules_end = round(height * .925)
            canvas.coords("rules", left, rules_y)
            canvas.itemconfigure("rules", width=right - left)
            title_fits = canvas.bbox("title")[3] <= round(height * .100)
            rules_fit = not description or canvas.bbox("rules")[3] <= rules_end
            bigger = min(limit, width + 26)
            if (title_fits and rules_fit) or bigger <= width or self.position(bigger, round(bigger / ratio)) is None:
                break
            width = bigger

        while canvas.bbox("title")[3] > round(height * .100) and title_font["size"] > 6:
            title_font.configure(size=title_font["size"] - 1)
        if canvas.bbox("title")[3] > round(height * .100):
            name = details["name"].replace("\n", " ")
            while len(name) > 1 and title_font.measure(name + "…") > right - title_x:
                name = name[:-1]
            canvas.itemconfigure("title", text=name + "…")

        canvas.configure(width=width, height=height)
        if frame:
            art = self.resize_photo(frame, width, height)
            canvas.images.append(art)
            canvas.create_image(0, 0, anchor="nw", image=art, tags="frame")
        else:
            canvas.create_rectangle(2, 2, width - 2, height - 2, fill=self.background, outline=accent,
                                    width=3, tags="frame")
            image = details.get("image")
            if image:
                scale = min(1, width * .82 / image.width(), height * .46 / image.height())
                art = self.resize_photo(image, round(image.width() * scale), round(image.height() * scale))
                canvas.images.append(art)
                canvas.create_image(width / 2, height * .335, image=art, tags="frame")
        canvas.tag_lower("frame")
        canvas.create_rectangle(left - 8, round(height * .025), right + 6, round(height * .099),
                                fill=self.background, outline="", tags="heading-background")
        canvas.tag_lower("heading-background", "title")
        if has_cost:
            block = min(23, round(height * .067))
            canvas.create_rectangle(left, head_y - block / 2, left + block, head_y + block / 2,
                                    fill=self.background, outline=accent, width=2, tags="cost-badge")
            canvas.create_text(left + block / 2, head_y, text=cost, font=self.heading_font,
                               fill=self.foreground, tags="cost")
        if description and not rules_fit:
            self.render_rules_view(canvas, description, left, right, rules_y, rules_end, details)

    def render_rules_view(self, canvas, description, left, right, top, bottom, details):
        canvas.delete("rules")
        text = tk.Text(canvas, font=self.body_font, background=self.background, foreground=self.foreground,
                       borderwidth=0, highlightthickness=0, takefocus=False, wrap="word", padx=0, pady=0, spacing3=2)
        text.insert("1.0", description)
        text.configure(state="disabled")
        self.rules_view = text
        canvas.create_text(right, bottom, text=details.get("scroll_hint") or "Shift+↕", font=self.body_font,
                           fill=self.muted, anchor="se", tags="scroll-hint")
        label_top = canvas.bbox("scroll-hint")[1]
        canvas.create_window(left, top, width=right - left, height=max(1, label_top - top - 2),
                             anchor="nw", window=text, tags="rules-viewport")

    def resize_photo(self, image, width, height):
        if (image.width(), image.height()) == (width, height):
            return image
        from PIL import Image, ImageTk

        resized = ImageTk.getimage(image).resize((width, height), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(resized, master=self.tree)

    def portrait(self, parent, image):
        art = tk.Label(parent, image=image, background=self.background, borderwidth=0, highlightthickness=0)
        art.image = image
        return art

    def position(self, width, height):
        mouse_x, mouse_y = self.point
        left, top = self.tree.winfo_vrootx(), self.tree.winfo_vrooty()
        right = left + self.tree.winfo_vrootwidth()
        bottom = top + self.tree.winfo_vrootheight()
        list_left = self.tree.winfo_rootx()
        list_right = list_left + self.tree.winfo_width()
        row_x, row_y, row_width, row_height = self.bounds(self.row)
        row_top = self.tree.winfo_rooty() + row_y
        row_bottom = row_top + row_height
        gap = 10
        if self.near_pointer:
            cell_left = list_left + row_x
            cell_right = cell_left + row_width
            center_x = max(left, min(right - width, mouse_x - width // 2))
            center_y = max(top, min(bottom - height, mouse_y - height // 2))
            adjacent = ((center_x, row_top - gap - height), (center_x, row_bottom + gap),
                        (cell_right + gap, center_y), (cell_left - gap - width, center_y))
            for x, y in adjacent:
                if left <= x <= right - width and top <= y <= bottom - height:
                    return f"+{x}+{y}"
            return None

        center_y = max(top, min(bottom - height, (row_top + row_bottom - height) // 2))
        if self.anchor_to_slot:
            list_left += row_x
            list_right = list_left + row_width
        center_x = max(left, min(right - width, (list_left + list_right - width) // 2))
        sides = [(list_right + gap, center_y), (list_left - gap - width, center_y)]
        vertical = [(row_top - gap - height, row_top - top), (row_bottom + gap, bottom - row_bottom)]
        above_below = [(center_x, y) for y, _ in sorted(vertical, key=lambda choice: -choice[1])]
        candidates = above_below + sides if self.anchor_to_slot else sides + above_below
        areas = []
        for widget in self.protected() if self.protected is not None else ():
            if widget.winfo_ismapped():
                x, y = widget.winfo_rootx(), widget.winfo_rooty()
                areas.append((x, y, x + widget.winfo_width(), y + widget.winfo_height()))
        if areas:
            outer_left = min(area[0] for area in areas)
            outer_top = min(area[1] for area in areas)
            outer_right = max(area[2] for area in areas)
            outer_bottom = max(area[3] for area in areas)
            candidates.extend(((outer_left - gap - width, center_y), (outer_right + gap, center_y),
                               (center_x, outer_top - gap - height), (center_x, outer_bottom + gap)))
        candidates.extend(((right - width, center_y), (left, center_y), (center_x, top), (center_x, bottom - height)))

        best, best_overlap = None, None
        for x, y in candidates:
            if not (left <= x <= right - width and top <= y <= bottom - height) or (
                    x <= mouse_x < x + width and y <= mouse_y < y + height):
                continue
            overlap = sum(max(0, min(x + width, r) - max(x, l)) * max(0, min(y + height, b) - max(y, t))
                          for l, t, r, b in areas)
            if overlap == 0:
                return f"+{x}+{y}"
            if best_overlap is None or overlap < best_overlap:
                best, best_overlap = (x, y), overlap
        return f"+{best[0]}+{best[1]}" if best is not None else None

    def watch_viewport(self):
        self.job = None
        if self.row_is_visible():
            self.job = self.tree.after(80, self.watch_viewport)
        else:
            self.hide()
