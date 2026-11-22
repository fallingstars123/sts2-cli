"""Display artwork straight from the installed game's PCK without exporting it."""

from functools import lru_cache
import hashlib
from io import BytesIO
import json
import re
import struct

from wiki_card_icons import COLORS as CARD_COLORS, WikiCardIcons, card_variant

MAP_ASSETS = {
    "battle": "map_monster", "elite": "map_elite", "chest": "map_chest",
    "rest": "map_rest", "shop": "map_shop", "event": "map_unknown",
}
MAP_ATLAS = "images/atlases/ui_atlas.sprites/map/"
CARD_ATLAS = "images/atlases/ui_atlas.sprites/card/"
TOP_BAR = "images/atlases/ui_atlas.sprites/top_bar/"
RESOURCE_PATHS = {"hp": "heart", "gold": "gold", "deck": "deck", "floor": "floor"}
CHARACTER_TABLE = "localization/eng/characters.json"
REGION = re.compile(rb"\bregion\s*=\s*Rect2\(\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\)")
ATLAS_PATH = re.compile(rb'\bpath="res://([^\"]+\.png)"')
TEXTURE_PATH = re.compile(rb'(?m)^path(?:\.(?:bptc|s3tc))?="res://([^\"]+\.ctex)"')
PACK_ERRORS = (OSError, ValueError, struct.error)


def texture_image(data):
    from PIL import Image

    if not data or not data.startswith(b"GST2") or len(data) < 52:
        return None
    width, height, _, encoding = struct.unpack_from("<HHII", data, 40)
    if not 1 <= width <= 4096 or not 1 <= height <= 4096:
        return None
    embedded = data[52:92]
    for signature in (b"RIFF", b"\x89PNG\r\n\x1a\n"):
        start = embedded.find(signature)
        if start >= 0:
            with Image.open(BytesIO(data[52 + start:])) as image:
                return image.convert("RGBA")
    formats = {17: b"DXT1", 18: b"DXT3", 19: b"DXT5", 22: b"DX10"}
    fourcc = formats.get(encoding)
    if not fourcc:
        return None
    size = ((width + 3) // 4) * ((height + 3) // 4) * (8 if encoding == 17 else 16)
    if 52 + size > len(data):
        return None
    # Godot's native BC texture payload is also the first mip level of a DDS texture.
    header = b"DDS " + struct.pack("<31I", 124, 0x81007, height, width, size, 0, 0, *([0] * 11),
                                   32, 4, int.from_bytes(fourcc, "little"), 0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0)
    if encoding == 22:
        header += struct.pack("<5I", 98, 3, 0, 1, 0)  # DXGI_FORMAT_BC7_UNORM, a 2D texture
    with Image.open(BytesIO(header + data[52:52 + size])) as image:
        return image.convert("RGBA")


class GameArt:
    def __init__(self, root, game_pack, entries, portrait, master):
        self.root, self.find_pack, self.read_entries = root, game_pack, entries
        self.read_portrait, self.master = portrait, master
        self.version = None
        self.index = {}
        self.photos = {}
        self.character_table = None
        self.portrait_pools = {}
        self.wiki_cards = WikiCardIcons(root / "STS2 Cache" / "wiki-cards")

    def refresh(self):
        pack = self.find_pack(self.root)
        try:
            version = (pack, pack.stat().st_mtime_ns) if pack else None
        except OSError:
            version = None
        if version == self.version:
            return
        self.version = version
        self.photos.clear()
        self.textures.cache_clear()
        self.index.clear()
        self.character_table = None
        self.portrait_pools.clear()
        if version:
            try:
                with pack.open("rb") as stream:
                    for name, offset, size, digest, flags in self.read_entries(stream):
                        if not flags and size <= 24_000_000:
                            self.index[name] = offset, size, digest
                            if name.startswith("images/packed/card_portraits/") and name.endswith(".png.import"):
                                pool, _, leaf = name.removeprefix("images/packed/card_portraits/").partition("/")
                                self.portrait_pools[leaf.rsplit("/", 1)[-1].removesuffix(".png.import")] = pool
            except PACK_ERRORS:
                self.index.clear()
                self.portrait_pools.clear()

    def read(self, key):
        if key not in self.index:
            return b""
        offset, size, digest = self.index[key]
        with self.version[0].open("rb") as stream:
            stream.seek(offset)
            data = stream.read(size)
        return data if len(data) == size and hashlib.md5(data).digest() == digest else b""

    def has_character(self, character):
        self.refresh()
        if self.character_table is None:
            try:
                data = json.loads(self.read(CHARACTER_TABLE))
                self.character_table = data if isinstance(data, dict) else None
            except PACK_ERRORS:
                return None
        return character.upper() + ".title" in self.character_table if self.character_table is not None else None

    @lru_cache(maxsize=7)
    def textures(self, key):
        return texture_image(self.read(key))

    def imported(self, key):
        target = TEXTURE_PATH.search(self.read(key + ".import"))
        return self.textures(target[1].decode("utf-8")) if target else None

    def atlas_sprite(self, key):
        data = self.read(key)
        path, region = ATLAS_PATH.search(data), REGION.search(data)
        if not path or not region:
            return None
        texture = self.imported(path[1].decode("utf-8"))
        x, y, width, height = map(int, region.groups())
        if texture and width > 0 and height > 0 and x + width <= texture.width and y + height <= texture.height:
            return texture.crop((x, y, x + width, y + height))
        return None

    def character_image(self, character, size, portrait=False):
        return self.photo(("character", character, size, portrait),
                          lambda: self.read_character(character, portrait), size)

    def read_character(self, character, portrait):
        from PIL import Image

        if not self.version:
            return None
        if not portrait:
            prefix = f".godot/imported/character_icon_{character.casefold()}.png-"
            entry = next((name for name in self.index if name.startswith(prefix) and name.endswith(".ctex")), None)
            if entry and (icon := self.textures(entry)):
                return icon
        data = self.read_portrait(self.version[0], character)
        if data:
            with Image.open(BytesIO(data)) as image:
                return image.convert("RGBA")
        return None

    def room_icon(self, room, detail, size):
        return self.photo(("room", room, detail, size), lambda: self.read_room(room, detail), size)

    def card_variant(self, identifier, pool, rarity, kind):
        entry = re.sub(r"^CARD[. :_-]+", "", identifier, flags=re.IGNORECASE).casefold()
        return card_variant(pool or self.portrait_pools.get(entry, ""), rarity, kind)

    def card_icon(self, variant, size):
        wiki_file = self.wiki_cards.find(variant)
        if wiki_file:
            icon = self.photo(("wiki-card", variant, size, wiki_file), lambda: self.read_image(wiki_file), size, local=True)
            if icon:
                return icon
        return self.photo(("card-badge", variant, size), lambda: self.card_badge(variant), size, local=True)

    @staticmethod
    def read_image(path):
        from PIL import Image

        with Image.open(path) as image:
            if image.width <= 128 and image.height <= 128:
                return image.convert("RGBA")
        return None

    @staticmethod
    def card_badge(variant):
        from PIL import Image, ImageDraw

        color, rarity, kind = variant
        image = Image.new("RGBA", (36, 48))
        draw = ImageDraw.Draw(image)
        edge = {"uncommon": "#9CC9D7", "rare": "#F0CA87", "ancient": "#D2A0F2", "event": "#9DDABE"}.get(rarity, "#CFD8DC")
        draw.rounded_rectangle((3, 2, 33, 46), radius=5, fill=CARD_COLORS[color], outline=edge, width=2)
        light = "#F8F4DF"
        if kind == "attack":
            draw.polygon([(22, 10), (27, 10), (27, 15), (15, 30), (10, 25)], fill=light)
            draw.line((9, 29, 16, 35), fill=light, width=3)
        elif kind == "skill":
            draw.polygon([(10, 14), (26, 14), (25, 26), (18, 34), (11, 26)], fill=light)
        elif kind == "power":
            draw.polygon([(18, 10), (25, 23), (18, 36), (11, 23)], fill=light)
        else:
            draw.ellipse((12, 16, 24, 30), outline=light, width=3)
        return image

    def resource_icon(self, name, character, size):
        def read():
            if name in RESOURCE_PATHS:
                return self.atlas_sprite(f"{TOP_BAR}top_bar_{RESOURCE_PATHS[name]}.tres")
            if name == "block":
                return self.imported("images/ui/combat/block.png")
            if name == "energy":
                return (self.atlas_sprite(f"{CARD_ATLAS}energy_{character.casefold()}.tres")
                        or self.atlas_sprite(f"{CARD_ATLAS}energy_colorless.tres"))
            if name == "potions":
                return self.imported("images/potions/large/energy_potion.png")
            return None

        return self.photo(("resource", name, character if name == "energy" else "", size), read, size)

    def relic_icon(self, identifier, size):
        if not re.fullmatch(r"[a-zA-Z0-9_]+", identifier):
            return None
        key = identifier.casefold()
        return self.photo(("relic", key, size), lambda: self.imported(f"images/relics/{key}.png"), size)

    def read_room(self, room, detail):
        if room in MAP_ASSETS:
            return self.atlas_sprite(f"{MAP_ATLAS}icons/{MAP_ASSETS[room]}.tres")
        identifier = detail.casefold() if isinstance(detail, str) and re.fullmatch(r"[a-zA-Z0-9_]+", detail) else ""
        if room == "start":
            name = "ancient_node_" + (identifier or "neow")
            icon = self.atlas_sprite(f"{MAP_ATLAS}ancients/{name}.tres")
            return icon or self.imported(f"images/packed/map/ancients/{name}.png")
        if room == "boss" and identifier:
            name = identifier.removesuffix("_boss") + "_boss_icon"
            icon = self.atlas_sprite(f"{MAP_ATLAS}placeholder/{name}.tres")
            return icon or self.imported(f"images/map/placeholder/{name}.png")
        return None

    def photo(self, key, read, size, local=False):
        if key not in self.photos:
            image = None
            if self.version or local:
                try:
                    from PIL import Image, ImageTk

                    source = read()
                    if source:
                        source = source.copy()
                        source.thumbnail(size, Image.Resampling.LANCZOS)
                        image = ImageTk.PhotoImage(source, master=self.master)
                except (ImportError, *PACK_ERRORS):
                    pass
            self.photos[key] = image
        return self.photos[key]
