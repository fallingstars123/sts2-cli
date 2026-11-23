"""Search and display the local card and relic dictionary."""

import tkinter as tk
from tkinter import ttk

from scroll_gestures import ScrollGestures

BOOK_LABELS = {
    "zh": ("卡牌与遗物图鉴", "搜索名称或 ID", "全部", "卡牌", "遗物", "没有找到匹配条目", "？表示随效果变化的数值"),
    "zh-TW": ("卡牌與遺物圖鑑", "搜尋名稱或 ID", "全部", "卡牌", "遺物", "找不到符合的項目", "？表示隨效果變動的數值"),
    "en": ("Card and relic dictionary", "Search by name or ID", "All", "Cards", "Relics", "No matching entries", "? marks a variable amount."),
    "ja": ("カード・レリック図鑑", "名前または ID で検索", "すべて", "カード", "レリック", "一致する項目がありません", "？は変動する値です。"),
    "ko": ("카드와 유물 도감", "이름 또는 ID 검색", "전체", "카드", "유물", "검색 결과 없음", "?는 변동하는 값입니다."),
    "es": ("Guía de cartas y reliquias", "Buscar por nombre o ID", "Todo", "Cartas", "Reliquias", "Sin resultados", "? indica un valor variable."),
    "fr": ("Guide des cartes et reliques", "Rechercher par nom ou ID", "Tout", "Cartes", "Reliques", "Aucun résultat", "? indique une valeur variable."),
    "de": ("Karten- und Reliktlexikon", "Nach Name oder ID suchen", "Alle", "Karten", "Relikte", "Keine Treffer", "? steht für einen variablen Wert."),
    "pt-BR": ("Guia de cartas e relíquias", "Buscar por nome ou ID", "Tudo", "Cartas", "Relíquias", "Nenhum resultado", "? indica um valor variável."),
    "it": ("Guida a carte e reliquie", "Cerca per nome o ID", "Tutto", "Carte", "Reliquie", "Nessun risultato", "? indica un valore variabile."),
    "ru": ("Справочник карт и реликвий", "Поиск по имени или ID", "Все", "Карты", "Реликвии", "Ничего не найдено", "? обозначает переменное значение."),
    "ar": ("دليل البطاقات والآثار", "ابحث بالاسم أو المعرّف", "الكل", "البطاقات", "الآثار", "لا توجد نتائج مطابقة", "تشير ؟ إلى قيمة متغيرة."),
    "hi": ("कार्ड और अवशेषों की सूची", "नाम या आईडी से खोजें", "सभी", "कार्ड", "अवशेष", "कोई मिलान नहीं मिला", "? बदलने वाली मात्रा दिखाता है।"),
    "id": ("Panduan kartu dan relik", "Cari nama atau ID", "Semua", "Kartu", "Relik", "Tidak ada hasil", "? menandai nilai yang berubah."),
    "tr": ("Kart ve kalıntı rehberi", "Ad veya kimlikle ara", "Tümü", "Kartlar", "Kalıntılar", "Eşleşme yok", "? değişken bir değeri gösterir."),
    "vi": ("Cẩm nang thẻ và di vật", "Tìm theo tên hoặc ID", "Tất cả", "Thẻ", "Di vật", "Không tìm thấy kết quả", "? biểu thị giá trị thay đổi."),
    "th": ("คู่มือการ์ดและวัตถุโบราณ", "ค้นหาด้วยชื่อหรือ ID", "ทั้งหมด", "การ์ด", "วัตถุโบราณ", "ไม่พบผลลัพธ์", "? หมายถึงค่าที่เปลี่ยนแปลงได้"),
}

DETAIL_LABELS = {
    "attack": ("攻击", "攻擊"), "skill": ("技能", "技能"), "power": ("能力", "能力"),
    "status": ("状态", "狀態"), "curse": ("诅咒", "詛咒"), "quest": ("任务", "任務"),
    "basic": ("初始", "初始"), "common": ("普通", "普通"), "uncommon": ("罕见", "罕見"),
    "rare": ("稀有", "稀有"), "ancient": ("先祖", "先祖"), "event": ("事件", "事件"),
    "starter": ("初始", "初始"), "shop": ("商店", "商店"),
}


def book_title(language):
    return BOOK_LABELS.get(language, BOOK_LABELS["en"])[0]


def detail_labels(entry, language):
    """Return localized type and rarity when the catalogue knows them."""
    values = (entry.type, entry.rarity)
    if language in ("zh", "zh-TW"):
        index = 0 if language == "zh" else 1
        return tuple(DETAIL_LABELS.get(str(value).casefold(), (value, value))[index] for value in values)
    return values


def preview_image(art, entry, *, card_size, relic_size):
    if entry.kind == "relic":
        return art.relic_icon(entry.id, relic_size)
    variant = art.card_variant(entry.id, entry.pool or "", entry.rarity or "", entry.type or "")
    return art.card_portrait(entry.id, entry.pool, variant, card_size)


def preview_description(entry, language, *, prefer_complete=False):
    if prefer_complete and entry.description_is_template and entry.observed_description:
        return entry.observed_description
    parts = [entry.description] if entry.description else []
    if entry.observed_description:
        labels = {"zh": "对局记录", "zh-TW": "對局記錄", "ja": "プレイ記録", "ko": "플레이 기록"}
        source = entry.observed_description_language
        label = labels.get(language, "Recorded in run")
        if source:
            label += f" · {source.upper()}"
        parts.append(f"{label}\n{entry.observed_description}")
    elif entry.description_is_template:
        parts.append(BOOK_LABELS.get(language, BOOK_LABELS["en"])[6])
    return "\n\n".join(parts)


class InventoryBook:
    def __init__(self, launcher, *, background, foreground, panel, border):
        self.launcher = launcher
        self.window = tk.Toplevel(launcher.root, background=background)
        self.window.geometry("760x525")
        self.window.minsize(520, 365)
        self.window.transient(launcher.root)
        self.window.grid_rowconfigure(1, weight=1)
        self.window.grid_columnconfigure(0, weight=1, minsize=190)
        self.window.grid_columnconfigure(1, weight=1, minsize=240)

        toolbar = ttk.Frame(self.window, padding=(14, 12))
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.grid_columnconfigure(1, weight=1)
        self.search_label = ttk.Label(toolbar)
        self.search_label.grid(row=0, column=0, padx=(0, 9), sticky="w")
        self.query = tk.StringVar(master=self.window)
        search = ttk.Entry(toolbar, textvariable=self.query)
        search.grid(row=0, column=1, sticky="ew")
        self.filter_box = ttk.Combobox(toolbar, state="readonly", width=12, style="Display.TCombobox")
        self.filter_box.grid(row=0, column=2, padx=(9, 0), sticky="e")
        self.filter_box.bind("<<ComboboxSelected>>", self.list_entries)

        list_panel = ttk.Frame(self.window)
        list_panel.grid(row=1, column=0, padx=(14, 6), pady=(0, 13), sticky="nsew")
        self.rows = ttk.Treeview(list_panel, show="tree", style="History.Treeview", selectmode="browse")
        self.rows.column("#0", width=200, stretch=True)
        self.rows.pack(side="left", fill="both", expand=True)
        list_scroll = ttk.Scrollbar(list_panel, orient="vertical", command=self.rows.yview,
                                    style="History.Vertical.TScrollbar")
        list_scroll.pack(side="right", fill="y")
        self.rows.configure(yscrollcommand=list_scroll.set)
        self.rows.bind("<<TreeviewSelect>>", self.show_entry)

        detail = ttk.Frame(self.window, style="Panel.TFrame", padding=14)
        detail.grid(row=1, column=1, padx=(6, 14), pady=(0, 13), sticky="nsew")
        self.name = ttk.Label(detail, style="PlayerName.TLabel")
        self.name.pack(anchor="w")
        self.meta = ttk.Label(detail, style="Caption.TLabel")
        self.meta.pack(anchor="w", pady=(3, 7))
        self.artwork = ttk.Label(detail, style="Caption.TLabel")
        self.artwork.pack(anchor="w", pady=(0, 7))
        self.description = tk.Text(detail, height=4, width=1, wrap="word", bg=panel, fg=foreground,
                                   font=launcher.fonts["body"], relief="flat", highlightthickness=0,
                                   selectbackground=border, state="disabled")
        self.description.pack(side="left", fill="both", expand=True)
        detail_scroll = ttk.Scrollbar(detail, orient="vertical", command=self.description.yview,
                                      style="History.Vertical.TScrollbar")
        detail_scroll.pack(side="right", fill="y")
        self.description.configure(yscrollcommand=detail_scroll.set)
        self.scrolling = ScrollGestures(self.rows), ScrollGestures(self.description)
        self.entries = {}
        self.query.trace_add("write", self.list_entries)
        self.refresh()
        search.focus_set()
        self.window.bind("<Escape>", lambda _event: self.window.destroy())

    def refresh(self):
        self.labels = BOOK_LABELS.get(self.launcher.language, BOOK_LABELS["en"])
        title, search, all_items, cards, relics, _, _ = self.labels
        self.window.title(title)
        self.search_label.configure(text=search)
        selected = max(0, self.filter_box.current())
        self.filter_box.configure(values=(all_items, cards, relics))
        self.filter_box.current(selected)
        self.list_entries()

    def list_entries(self, *_event):
        selected = self.rows.selection()
        kind = (None, "card", "relic")[max(0, self.filter_box.current())]
        entries = self.launcher.inventory_catalog.search(self.query.get(), self.launcher.language, kind=kind)
        self.rows.delete(*self.rows.get_children())
        self.entries = {}
        for entry in entries:
            key = f"{entry.kind}:{entry.id}"
            self.entries[key] = entry
            self.rows.insert("", "end", iid=key, text=entry.name)
        if self.entries:
            key = selected[0] if selected and selected[0] in self.entries else next(iter(self.entries))
            self.rows.selection_set(key)
            self.rows.see(key)
        self.show_entry()

    def show_entry(self, _event=None):
        selected = self.rows.selection()
        entry = self.entries.get(selected[0]) if selected else None
        self.description.configure(state="normal")
        self.description.delete("1.0", "end")
        if entry is None:
            self.name.configure(text=self.labels[5])
            self.meta.configure(text="")
            self.artwork.configure(image="")
        else:
            kind, rarity = detail_labels(entry, self.launcher.language)
            meta = [str(value) for value in (entry.energy, kind, rarity, entry.id) if value is not None and value != ""]
            self.name.configure(text=entry.name)
            self.meta.configure(text="  ·  ".join(meta))
            picture = preview_image(self.launcher.art, entry, card_size=(215, 150), relic_size=(100, 100))
            self.artwork.configure(image=picture or "")
            self.description.insert("end", preview_description(entry, self.launcher.language))
        self.description.yview_moveto(0)
        self.description.configure(state="disabled")
