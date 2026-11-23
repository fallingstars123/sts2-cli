"""Offline inventory names, descriptions, and archive observations."""

from dataclasses import dataclass
import json
from pathlib import Path
import re
from unicodedata import normalize


TABLES = {"card": "cards", "relic": "relics", "potion": "potions", "keyword": "card_keywords"}
PACK_LOCALES = {
    "en": "eng", "zh": "zhs", "zh-cn": "zhs", "zh-hans": "zhs", "zh-tw": "zht", "zh-hant": "zht",
    "de": "deu", "es": "esp", "es-419": "spa", "fr": "fra", "id": "ind", "it": "ita", "ja": "jpn",
    "ko": "kor", "pl": "pol", "pt": "ptb", "pt-br": "ptb", "ru": "rus", "th": "tha", "tr": "tur",
}
UI_LOCALES = {locale: code for code, locale in PACK_LOCALES.items() if "-" not in code}
UI_LOCALES.update(zht="zh-TW", spa="es-419", ptb="pt-BR")
PACK_LOCALE_CODES = frozenset(PACK_LOCALES.values())
PREFIX = re.compile(r"^(?:(?:CARD|RELIC)[. :_-]+|POTION[. :]+)", re.IGNORECASE)
IDENTIFIER = re.compile(r"[A-Z0-9_]{1,96}")
MARKUP = re.compile(r"\[/?(?:b|i|u|s|h[1-6]|color|gold|green|blue|purple|red|orange|gray|grey|"
                    r"white|yellow|rainbow|url|center|right|left|wave|shake|pulse|sine)(?:=[^\]\n]*)?\]", re.IGNORECASE)
FIELD = re.compile(r"([A-Za-z][A-Za-z0-9_]*)(?::(.*))?", re.DOTALL)
MATCHABLE_FIELD = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)(?::(diff\(\)|plural:[^{}]+|(?:energy|star)Icons\(\d*\)))?\}")
LEGACY_FIELD = re.compile(r"\[([A-Za-z][A-Za-z0-9_]*(?::[^\]\n]+)?)\]")
RESOURCE_ICON = re.compile(r"(energy|star)Icons\(\d*\)", re.IGNORECASE)
PACKED_ICON_PATH = r"\[img\]res://images/packed/sprite_fonts/(?:[a-z0-9]+_)*"
PACKED_ICON_END = r"_icon\.png\[/img\]"
PACKED_ICONS = re.compile(rf"{PACKED_ICON_PATH}(?P<resource>energy|star){PACKED_ICON_END}"
                          rf"(?:{PACKED_ICON_PATH}(?P=resource){PACKED_ICON_END})*", re.IGNORECASE)
RESOURCE_TOKEN = re.compile(r"\[(energy|star):(\d{1,4})\]", re.IGNORECASE)
KEYWORD_LINE = re.compile(r"\[gold\](.+?)\[/gold\][.。]?", re.IGNORECASE)


@dataclass(frozen=True)
class InventoryEntry:
    kind: str
    id: str
    name: str
    description: str
    type: str | None = None
    energy: int | str | None = None
    rarity: str | None = None
    pool: str | None = None
    upgraded: bool = False
    description_is_template: bool = False
    name_language: str | None = None
    description_language: str | None = None
    observed: bool = False
    observed_description: str = ""
    observed_description_language: str | None = None


def _kind(value):
    if isinstance(value, str):
        return {"card": "card", "cards": "card", "deck": "card", "relic": "relic", "relics": "relic",
                "potion": "potion", "potions": "potion"}.get(value)
    return None


def _entry_id(value):
    if isinstance(value, str):
        identifier = PREFIX.sub("", value.strip()).removesuffix("+").upper()
        if IDENTIFIER.fullmatch(identifier):
            return identifier
    return None


def _locale_code(value):
    if not isinstance(value, str):
        return None
    code = value.replace("_", "-").casefold()
    if code in PACK_LOCALE_CODES:
        return code
    return PACK_LOCALES.get(code, PACK_LOCALES.get(code.partition("-")[0]))


def _locale(value):
    return _locale_code(value) or "eng"


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _plain(value):
    return MARKUP.sub("", _text(value)).strip()


def _resource_tokens(text):
    return PACKED_ICONS.sub(lambda match: f"[{match['resource'].lower()}:{match[0].lower().count('[/img]')}]", text)


def _resource_amount(resource, amount, locale):
    if locale in ("zhs", "zht"):
        unit = "星" if resource == "star" else "点能量"
    else:
        unit = " Stars" if resource == "star" else " Energy"
    return f"{amount}{unit}"


def _numbers(item):
    values = {}
    for source in (item.get("vars"), item.get("stats")):
        if isinstance(source, dict):
            values.update({key.casefold(): value for key, value in source.items()
                           if isinstance(key, str) and type(value) is int})
    return values


def _matched_numbers(template, recorded):
    """Extract only unambiguous integer fields from a complete same-locale match."""
    template = " ".join(_plain(template).split())
    recorded = " ".join(_resource_tokens(_plain(recorded)).split())
    if not template or not recorded or max(len(template), len(recorded)) > 4000:
        return {}

    pattern, fields, cursor = [], [], 0
    for field in MATCHABLE_FIELD.finditer(template):
        literal = template[cursor:field.start()]
        if (not literal and fields) or (literal and literal[-1].isdigit()):
            return {}
        if "{" in literal or "}" in literal:
            return {}
        cursor = field.end()
        if cursor < len(template) and template[cursor].isdigit():
            return {}
        rule = field[2] or ""
        forms = rule.removeprefix("plural:").split("|") if rule.startswith("plural:") else None
        if forms is not None and (len(forms) != 2 or not all(forms)):
            return {}
        if forms:
            capture = "(" + "|".join(map(re.escape, forms)) + ")"
        elif icon := RESOURCE_ICON.fullmatch(rule):
            capture = rf"\[{icon[1].lower()}:([0-9]{{1,4}})\]"
        else:
            capture = r"(-?(?:0|[1-9][0-9]{0,8}))"
        pattern.extend((re.escape(literal), capture))
        fields.append((field[1].casefold(), forms))
    remaining = template[cursor:]
    if not fields or "{" in remaining or "}" in remaining:
        return {}
    pattern.append(re.escape(remaining))
    match = re.fullmatch("".join(pattern), recorded)
    if match is None:
        return {}

    values = {}
    for (name, forms), captured in zip(fields, match.groups()):
        if forms is not None:
            continue
        amount = int(captured)
        if name in values and values[name] != amount:
            return {}
        values[name] = amount
    for (name, forms), captured in zip(fields, match.groups()):
        if forms is not None and (name not in values or captured != forms[0 if values[name] == 1 else 1]):
            return {}
    return values


def _format_field(field, numbers, locale):
    parsed = FIELD.fullmatch(field)
    if not parsed:
        return "?", True
    key, operation = parsed.groups()
    key = key.casefold()
    value = numbers.get(key)
    if key == "incombat" and operation and operation.endswith("|"):
        return "", False
    if operation and (icon := RESOURCE_ICON.fullmatch(operation)):
        resource = icon[1].casefold()
        if key in ("energyprefix", "starprefix"):
            return _resource_amount(resource, "", locale), False
        return _resource_amount(resource, value if value is not None else "?", locale), value is None
    if operation and operation.startswith("plural:"):
        forms = operation.removeprefix("plural:").split("|")
        if value is not None and len(forms) == 2 and not any("{" in form for form in forms):
            return forms[0 if value == 1 else 1], False
    if operation in (None, "diff()", "abs()") and value is not None:
        return str(abs(value) if operation == "abs()" else value), False
    if key == "energyprefix" and operation is None:
        return "", False
    return "?", True


def _description(text, numbers, locale):
    text = _resource_tokens(_plain(text))
    text = RESOURCE_TOKEN.sub(lambda match: _resource_amount(match[1].casefold(), match[2], locale), text)
    parts, cursor, unresolved = [], 0, False
    while (start := text.find("{", cursor)) != -1:
        parts.append(text[cursor:start])
        end, depth = start + 1, 1
        while end < len(text) and depth:
            char = text[end]
            depth += (char == "{") - (char == "}")
            end += 1
        if depth:
            parts.append("?")
            unresolved = True
            cursor = len(text)
            break
        value, missing = _format_field(text[start + 1:end - 1], numbers, locale)
        parts.append(value)
        unresolved = unresolved or missing
        cursor = end
    parts.append(text[cursor:])

    def legacy(match):
        nonlocal unresolved
        variable = match[1]
        if ":" in variable and "|" in variable and ":plural:" not in variable:
            key, forms = variable.split(":", 1)
            variable = f"{key}:plural:{forms}"
        value, missing = _format_field(variable, numbers, locale)
        unresolved = unresolved or missing
        return value

    output = LEGACY_FIELD.sub(legacy, "".join(parts))
    return output.strip(), unresolved


def display_description(text, language):
    """Normalize a complete description for display or comparison with a local render."""
    return _description(text, {}, _locale(language))[0]


def _energy(item):
    if item.get("energy_x") is True or item.get("cost_x") is True:
        return "X"
    for key in ("energy_cost", "card_cost", "cost"):
        value = item.get(key)
        if value == "X":
            return "X"
        if type(value) is int and value >= 0:
            return value
    return None


def _upgraded(item):
    return (item.get("upgraded") is True or item.get("is_upgraded") is True
            or (type(item.get("upgrade")) is int and item["upgrade"] > 0))


def _tagged(value):
    if not isinstance(value, dict):
        return {}
    return {code: item for key, item in value.items() if (code := _locale_code(key))
            and isinstance(item, str) and item.strip()}


def _fold(text):
    return " ".join(normalize("NFKC", text).casefold().replace("_", " ").split())


def _json_object(source):
    try:
        data = json.loads(source)
    except (ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def _objects(value):
    if isinstance(value, list):
        yield from (item for item in value if isinstance(item, dict))


class InventoryCatalog:
    """Use installed game localization for the dictionary and exact run records for hover details."""

    def __init__(self, root, *, art=None):
        self.root = Path(root)
        self.art = art
        self.version = None
        self.tables = {}
        self.observations = {}
        self.archive_signature = None
        self.archive_offsets = {}
        self.refresh()

    def refresh(self):
        if self.art is not None:
            try:
                self.art.refresh()
            except (OSError, ValueError):
                pass
        version = getattr(self.art, "version", None)
        if version != self.version:
            self.version = version
            self.tables.clear()

    def _table(self, kind, locale):
        key = kind, locale
        if key in self.tables:
            return self.tables[key]
        filename = TABLES[kind] + ".json"
        try:
            table = _json_object(self.art.read(f"localization/{locale}/{filename}")) if self.art else {}
        except (OSError, ValueError):
            table = {}
        if not table:
            try:
                table = _json_object((self.root / f"localization_{locale}" / filename).read_bytes())
            except OSError:
                pass
        self.tables[key] = table
        return table

    def _localized(self, kind, identifier, suffix, locale, item):
        key = f"{identifier}.{suffix}"
        item_value = item.get("name" if suffix == "title" else suffix)
        values = _tagged(item_value)
        if isinstance(item_value, str) and item_value.strip():
            explicit = item.get("language")
            if code := _locale_code(explicit):
                values[code] = item_value
            else:
                for code in dict.fromkeys((locale, "eng", "zhs", "zht")):
                    title = _plain(self._table(kind, code).get(f"{identifier}.title"))
                    name = item.get("name") or item.get("title")
                    if title and isinstance(name, str) and _plain(name).removesuffix("+") == title:
                        values[code] = item_value
                if not values and not self._table(kind, "eng").get(f"{identifier}.title"):
                    values[None] = item_value

        numbers = {}
        keywords = {}
        if suffix == "description":
            conflicting = set()
            for code, recorded in values.items():
                if code is None:
                    continue
                source = self._table(kind, code).get(key)
                body, suffixes = self._split_keywords(recorded, code) if kind == "card" else (recorded, ())
                matched = _matched_numbers(source, body)
                if suffixes and (matched or _plain(source) == _plain(body)):
                    keywords.update(dict.fromkeys(suffixes))
                for variable, amount in matched.items():
                    if variable in numbers and numbers[variable] != amount:
                        conflicting.add(variable)
                    numbers[variable] = amount
            for variable in conflicting:
                numbers.pop(variable)
            numbers.update(_numbers(item))
        modes = (locale, "zhs", "eng", None) if locale == "zht" else (locale, "eng", "zhs", None)
        for code in dict.fromkeys(modes):
            local = _text(self._table(kind, code).get(key)) if code else ""
            observed = _text(values.get(code))
            if suffix == "title":
                if local or observed:
                    return _plain(local or observed).removesuffix("+"), False, code, not bool(local)
                continue
            declared, incomplete = _description(local, numbers, code)
            seen, seen_incomplete = _description(observed, numbers, code)
            if seen and (not declared or not seen_incomplete):
                return seen, seen_incomplete, code, True
            if declared:
                translated = [_plain(self._table("keyword", code).get(keyword)) for keyword in keywords]
                declared = "\n".join([declared, *filter(None, translated)])
                return declared, incomplete, code, bool(numbers)
            if seen:
                return seen, seen_incomplete, code, True
        return "", False, None, False

    def _split_keywords(self, description, locale):
        lines = description.strip().splitlines()
        titles = None
        keywords = []
        while len(lines) > 1 and (match := KEYWORD_LINE.fullmatch(lines[-1].strip())):
            if titles is None:
                titles = {_plain(value): key for key, value in self._table("keyword", locale).items()
                          if key.endswith(".title")}
            keyword = titles.get(_plain(match[1]))
            if not keyword:
                break
            keywords.append(keyword)
            lines.pop()
        return "\n".join(lines), tuple(reversed(keywords))

    def _card_reference_values(self, identifier, locale, upgraded, known_energy):
        read_metadata = getattr(self.art, "rendered_card_metadata", None)
        if not callable(read_metadata):
            return {}, None
        key = f"{identifier}.description"
        for code in dict.fromkeys((locale, "eng", "zhs")):
            metadata = read_metadata(identifier, code, upgraded)
            reference = _text(metadata.get("description"))
            energy = _energy(metadata)
            if not reference or (known_energy is not None and known_energy != energy):
                continue
            template = self._table("card", code).get(key)
            amounts = _matched_numbers(template, reference)
            text, incomplete = _description(template, amounts, code)
            reference_text, reference_incomplete = _description(reference, {}, code)
            if (text and not incomplete and not reference_incomplete
                    and " ".join(text.split()) == " ".join(reference_text.split())):
                return amounts, energy
        return {}, None

    def _potion_id_from_title(self, item, locale="eng"):
        name = item.get("name") or item.get("title")
        candidates = _tagged(name)
        if isinstance(name, str) and name.strip():
            explicit = _locale_code(item.get("language"))
            candidates = {code: name for code in ((explicit,) if explicit else (locale, "eng", "zhs", "zht"))}
        matches = set()
        for code, title in candidates.items():
            normalized = _fold(_plain(title))
            if not normalized:
                continue
            for token, value in self._table("potion", code).items():
                if token.endswith(".title") and _fold(_plain(value)) == normalized:
                    if identifier := _entry_id(token.removesuffix(".title")):
                        matches.add(identifier)
        return matches.pop() if len(matches) == 1 else None

    def lookup(self, kind, identifier, language="en", *, observed=None):
        kind, key = _kind(kind), _entry_id(identifier)
        if kind is None:
            return None
        direct = observed if isinstance(observed, dict) else {}
        locale = _locale(language)
        if kind == "potion":
            explicit = _entry_id(direct.get("id") or direct.get("potion_id"))
            key = explicit or key or self._potion_id_from_title(direct, locale)
        if key is None:
            return None
        upgraded = _upgraded(direct) or (isinstance(identifier, str) and identifier.strip().endswith("+"))
        scoped = self.observations.get((kind, key, upgraded), (0, {}))[1]
        item = {**scoped, **{field: value for field, value in direct.items() if value is not None}}
        description_item = item
        if scoped.get("description") and not direct.get("description"):
            # An ID-only deck row can have a generated name unrelated to the observed text's language.
            source_fields = ("description", "name", "title", "language")
            description_item = {**item, **{field: scoped.get(field) for field in source_fields}}
        name, _, name_locale, _ = self._localized(kind, key, "title", locale, item)
        description, template, desc_locale, seen = self._localized(kind, key, "description", locale, description_item)
        recorded_energy = _energy(item) if kind == "card" else None
        energy = recorded_energy
        if (kind == "card" and direct and (template or energy is None)
                and not description_item.get("description") and not _numbers(description_item)):
            # Native deck snapshots can contain only the ID and upgrade flag until the card is seen in combat.
            amounts, reference_energy = self._card_reference_values(key, locale, upgraded, energy)
            if amounts and template:
                description, template, desc_locale, _ = self._localized(
                    kind, key, "description", locale, {**description_item, "vars": amounts},
                )
            if energy is None and not template:
                energy = reference_energy
        alternate, alternate_language = "", None
        if template and description_item.get("description"):
            scopes = dict.fromkeys(("eng", "zhs", "zht", *_tagged(description_item["description"])))
            for code in scopes:
                if code != desc_locale:
                    text, incomplete, actual, from_record = self._localized(kind, key, "description", code, description_item)
                    if text and not incomplete and from_record and actual != desc_locale:
                        alternate, alternate_language = text, UI_LOCALES.get(actual)
                        break
        pool = _text(item.get("pool"))
        if kind == "card" and not pool and self.art is not None:
            pool = self.art.portrait_pools.get(key.casefold(), "")
        return InventoryEntry(kind=kind, id=key, name=name or key.replace("_", " ").title(), description=description,
                              type=_text(item.get("type")) or None, energy=energy, rarity=_text(item.get("rarity")) or None,
                              pool=pool or None, upgraded=upgraded, description_is_template=template,
                              name_language=UI_LOCALES.get(name_locale), description_language=UI_LOCALES.get(desc_locale),
                              observed=seen or recorded_energy is not None or bool(alternate), observed_description=alternate,
                              observed_description_language=alternate_language)

    def search(self, query="", language="en", *, kind=None):
        self.refresh()
        locale = _locale(language)
        kinds = ("card", "relic") if kind is None else (_kind(kind),)
        query = _fold(query) if isinstance(query, str) else ""
        words = query.split()
        ranked = []
        for group in kinds:
            if group not in TABLES:
                continue
            tables = [self._table(group, code) for code in dict.fromkeys((locale, "eng", "zhs", "zht"))]
            ids = {key.removesuffix(".title") for table in tables for key, value in table.items()
                   if isinstance(key, str) and key.endswith(".title") and _text(value)}
            ids.update(identifier for candidate, identifier, _ in self.observations if candidate == group)
            for identifier in ids:
                options = [_fold(identifier)] + [_fold(_plain(table.get(f"{identifier}.title"))) for table in tables]
                if any(not any(word in option for option in options) for word in words):
                    continue
                item = self.lookup(group, identifier, language)
                if item is not None:
                    rank = 0 if query in options else 1 if any(option.startswith(query) for option in options) else 2
                    ranked.append((rank, _fold(item.name), group, identifier, item))
        return [item[-1] for item in sorted(ranked, key=lambda row: row[:-1])]

    def observe_archive(self, folder):
        """Refresh the selected archive's observations without loading other runs."""
        signature = {}
        if folder is not None:
            try:
                folder = Path(folder)
                candidates = [folder] if folder.is_file() else sorted(folder.glob("*.jsonl"))
                for path in candidates:
                    if path.name.endswith(".plan.jsonl"):
                        continue
                    stat = path.stat()
                    signature[path] = stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size
            except (OSError, TypeError, ValueError):
                pass
        if signature == self.archive_signature:
            return len(self.observations)
        previous = self.archive_signature
        if previous is None or any(path not in signature or signature[path][:2] != stat[:2]
                                   or signature[path][3] < stat[3]
                                   or (signature[path][3] == stat[3] and signature[path][2] != stat[2])
                                   for path, stat in previous.items()):
            self.observations.clear()
            self.archive_offsets.clear()
        complete = True
        for path in signature:
            try:
                with path.open("rb") as records:
                    records.seek(self.archive_offsets.get(path, 0))
                    while line := records.readline():
                        row = _json_object(line)
                        if not row and not line.endswith(b"\n"):
                            break
                        self._observe_row(row)
                        self.archive_offsets[path] = records.tell()
            except OSError:
                complete = False
        self.archive_signature = signature if complete else None
        return len(self.observations)

    def _observe_row(self, row):
        data = row.get("data") if row.get("type") == "state" else row.get("state")
        if not isinstance(data, dict):
            return
        for player in (data.get("player"), row.get("run")):
            if isinstance(player, dict):
                for item in _objects(player.get("deck")):
                    self._observe("card", item, 3)
                for item in _objects(player.get("relics")):
                    self._observe("relic", item, 3)
                for item in _objects(player.get("potions")):
                    self._observe("potion", item, 3)
        for item in _objects(data.get("hand")):
            self._observe("card", item, 0)
        overlay = data.get("steam_state")
        for screen in (data, overlay):
            if not isinstance(screen, dict):
                continue
            for item in _objects(screen.get("cards")):
                card = item.get("card")
                if not isinstance(card, dict):
                    card = item
                    if screen.get("decision") == "shop" and "card_cost" not in card:
                        card = {key: value for key, value in card.items() if key != "cost"}
                self._observe("card", card, 2)
            for item in _objects(screen.get("items")):
                if isinstance(card := item.get("card"), dict):
                    self._observe("card", card, 2)
            for item in _objects(screen.get("relics")):
                self._observe("relic", item, 2)
            for item in _objects(screen.get("potions")):
                self._observe("potion", item, 2)

    def _observe(self, kind, item, priority):
        identifier = _entry_id(item.get("id") or item.get("card_id") or item.get("potion_id"))
        if identifier is None and kind == "potion":
            identifier = self._potion_id_from_title(item)
        if identifier is None:
            return
        selected = {key: item[key] for key in ("name", "title", "description", "energy_x", "cost_x", "cost",
                    "card_cost", "energy_cost", "stats", "vars", "type", "rarity", "pool", "language")
                    if item.get(key) is not None}
        if "title" in selected and "name" not in selected:
            selected["name"] = selected["title"]
        score = (priority + 8 * bool(_numbers(selected)) + 5 * bool(selected.get("description"))
                 + 3 * (_energy(selected) is not None if kind == "card" else False))
        key = kind, identifier, _upgraded(item)
        old_score, old = self.observations.get(key, (-1, {}))
        if score >= old_score:
            merged = {**{k: old[k] for k in ("type", "rarity", "pool") if k in old}, **selected}
        else:
            merged = {**{k: selected[k] for k in ("type", "rarity", "pool") if k in selected}, **old}
        if kind == "card" and "X" in (_energy(selected), _energy(old)):
            merged["energy_x"] = True
        self.observations[key] = max(score, old_score), merged
