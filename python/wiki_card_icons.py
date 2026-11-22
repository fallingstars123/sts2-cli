"""Map card metadata to badge colors and optional, previously cached Wiki badges."""


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


def cached_badge(directory, variant):
    if variant in WIKI_KEYS:
        path = directory / filename(variant)
        if path.is_file():
            return path
    return None
