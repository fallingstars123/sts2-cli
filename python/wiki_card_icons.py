"""Select and cache the pre-made card badges from the Huiji STS2 Wiki."""

from hashlib import md5
from queue import Empty, SimpleQueue
from threading import Thread
from urllib.request import Request, urlopen
from uuid import uuid4


POOL_COLORS = {
    "ironclad": "red", "silent": "green", "defect": "blue", "regent": "orange",
    "necrobinder": "purple", "fool": "colorless", "colorless": "colorless", "status": "colorless",
    "event": "event", "curse": "curse", "quest": "quest",
}
COLORS = {
    "red": "#9A3E4B", "green": "#4A824C", "blue": "#387B9E", "orange": "#AD703A",
    "purple": "#804F9D", "colorless": "#66707B", "event": "#597D7B", "curse": "#4C435B", "quest": "#BD9347",
}
KINDS = {"a": "attack", "s": "skill", "p": "power", "q": "quest", "c": "curse"}
WIKI_VARIANTS = {
    "red": {"common": "as", "uncommon": "asp", "rare": "asp", "ancient": "ap", "event": "as"},
    "green": {"common": "as", "uncommon": "asp", "rare": "asp", "ancient": "ap", "event": "sp"},
    "blue": {"common": "as", "uncommon": "asp", "rare": "asp", "ancient": "sp", "event": "asp"},
    "orange": {"common": "as", "uncommon": "asp", "rare": "asp", "ancient": "ap"},
    "purple": {"common": "as", "uncommon": "asp", "rare": "asp", "ancient": "ap"},
    "colorless": {"common": "as", "uncommon": "asp", "rare": "asp", "ancient": "ap"},
    "event": {"event": "asp", "ancient": "as"}, "curse": {"curse": "c"}, "quest": {"quest": "q"},
}
WIKI_KEYS = frozenset((color, rarity, KINDS[code]) for color, classes in WIKI_VARIANTS.items()
                      for rarity, kinds in classes.items() for code in kinds)
PNG = b"\x89PNG\r\n\x1a\n"


def card_variant(pool, rarity, kind):
    base = pool.casefold().replace("_", "").removesuffix("cardpool")
    color = POOL_COLORS.get(base, "colorless")
    rarity, kind = rarity.casefold(), kind.casefold()
    if "curse" in (color, rarity, kind):
        return "curse", "curse", "curse"
    if "quest" in (color, rarity, kind):
        return "quest", "quest", "quest"
    if rarity == "status" or kind == "status":
        return "colorless", "common", "skill"
    if rarity not in ("uncommon", "rare", "ancient", "event"):
        rarity = "common"
    if kind not in ("attack", "skill", "power"):
        kind = "skill"
    if color == "event" and rarity != "ancient" or color == "colorless" and rarity == "event":
        return "event", "event", kind
    return color, rarity, kind


def filename(variant):
    return "Card_" + "_".join(variant) + ".png"


def icon_url(variant):
    leaf = filename(variant)
    code = md5(leaf.encode()).hexdigest()[:2]
    return f"https://huiji-thumb.huijistatic.com/sts2/uploads/thumb/{code[0]}/{code}/{leaf}/36px-{leaf}"


def download_icon(variant):
    request = Request(icon_url(variant), headers={"User-Agent": "sts2-cli/0.1.3 (Huiji Wiki icons)"})
    with urlopen(request, timeout=4) as response:
        data = response.read(32_769)
    if not data.startswith(PNG) or not 24 <= len(data) <= 32_768:
        raise ValueError("Unexpected Wiki icon payload")
    return data


class WikiCardIcons:
    def __init__(self, directory):
        self.directory = directory
        self.pending = set()
        self.attempted = set()
        self.results = SimpleQueue()
        self.revision = 0

    def find(self, variant):
        if variant in WIKI_KEYS:
            path = self.directory / filename(variant)
            if path.is_file():
                return path
        return None

    def request(self, variants):
        batch = [variant for variant in dict.fromkeys(variants)
                 if variant in WIKI_KEYS and variant not in self.attempted and not self.find(variant)]
        if batch:
            self.attempted.update(batch)
            self.pending.update(batch)
            Thread(target=self.fetch, args=(batch,), daemon=True).start()

    def fetch(self, batch):
        for variant in batch:
            saved = False
            temporary = None
            try:
                data = download_icon(variant)
                self.directory.mkdir(parents=True, exist_ok=True)
                path = self.directory / filename(variant)
                temporary = path.with_name(f".{path.stem}-{uuid4().hex}.tmp")
                temporary.write_bytes(data)
                temporary.replace(path)
                saved = True
            except (OSError, ValueError):
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
            self.results.put((variant, saved))

    def poll(self):
        while True:
            try:
                variant, saved = self.results.get_nowait()
            except Empty:
                return
            self.pending.discard(variant)
            self.revision += saved
