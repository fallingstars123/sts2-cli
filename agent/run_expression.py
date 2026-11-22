"""Profiles and player-facing messages for a run's optional AI commentary."""

import json
from pathlib import Path
from re import fullmatch
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROVIDER_MODELS = {"DeepSeek": "deepseek-flash", "Claude": "claude-sonnet-5-5"}
MODEL_CHOICES = {
    "DeepSeek": ("deepseek-flash", "deepseek-v4-pro"),
    "Claude": ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"),
}
LANGUAGE_NAMES = {
    "zh": "简体中文", "zh-TW": "繁體中文", "en": "English", "ja": "日本語", "ko": "한국어",
    "es": "Español", "fr": "Français", "de": "Deutsch", "pt-BR": "Português (Brasil)",
    "it": "Italiano", "ru": "Русский", "ar": "العربية", "hi": "हिन्दी",
    "id": "Bahasa Indonesia", "tr": "Türkiye Türkçesi", "vi": "Tiếng Việt", "th": "ไทย",
}
SPEECH_LANGUAGES = tuple(LANGUAGE_NAMES.values())
CHARACTERS = ("Ironclad", "Silent", "Defect", "Regent", "Necrobinder")
STARTERS = {
    "scout": ("斥候", "斥候", "Scout", "DeepSeek", "A practical scout at the table. Be observant, direct and lightly playful."),
    "strategist": ("谋士", "謀士", "Strategist", "Claude", "A thoughtful companion at the table. Be warm, curious and concise."),
}


def preferences(path):
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def profile_for(path, card_id, provider, ui_language):
    data = preferences(path)
    interface = data.get("ui_language")
    if isinstance(interface, str) and interface in LANGUAGE_NAMES:
        ui_language = interface
    card = catalog_from(data, ui_language).get(card_id) or clean_card({"provider": provider}, provider)
    return {**card, "language": card["language"] or default_speech(data, ui_language)}


def clean_card(saved, default_name):
    def field(name, default, limit):
        value = saved.get(name)
        return value.strip()[:limit] if isinstance(value, str) and value.strip() else default

    provider = saved.get("provider")
    if not isinstance(provider, str) or provider not in PROVIDER_MODELS:
        provider = "DeepSeek"
    character = saved.get("character")
    ascension = saved.get("ascension")
    return {
        "provider": provider,
        "model": field("model", PROVIDER_MODELS[provider], 120),
        "enabled": saved.get("enabled") is not False,
        "character": character if character in CHARACTERS else "Ironclad",
        "ascension": ascension if type(ascension) is int and 0 <= ascension <= 10 else 0,
        "trial": saved.get("trial") is not False,
        "name": field("name", default_name, 48),
        "language": field("language", "", 48),
        "identity": field("identity", "", 1000),
    }


def default_speech(data, ui_language):
    value = data.get("output_language")
    if isinstance(value, str) and value.strip():
        return value.strip()[:48]
    return LANGUAGE_NAMES.get(ui_language, "English")


def cards_in(data):
    cards = data.get("cards")
    if not isinstance(cards, dict):
        return {}
    return {key: value for key, value in cards.items()
            if isinstance(value, dict) and isinstance(value.get("name"), str) and value["name"].strip()}


def catalog(path, ui_language):
    return catalog_from(preferences(path), ui_language)


def catalog_from(data, ui_language):
    cards = {}
    for key, (zh, traditional, en, provider, identity) in STARTERS.items():
        name = {"zh": zh, "zh-TW": traditional}.get(ui_language, en)
        cards[key] = clean_card({"provider": provider, "identity": identity}, name)
    for key, saved in cards_in(data).items():
        cards[key] = clean_card(saved, saved["name"])
    return cards


def expression_prompt(profile):
    if not profile["enabled"]:
        return "Player-facing commentary is off for this decision. Omit the message field."
    persona = json.dumps({key: profile[key] for key in ("name", "language", "identity")}, ensure_ascii=False)
    return ("Player-facing commentary is optional. If you want to say something, add one short "
            "`message` string to the JSON reply, written in the profile language. Use the current game "
            "situation and any estimate as background, and choose the topic yourself. The identity card "
            "guides the voice of this message only. Profile: " + persona)


def reply_message(reply, profile):
    value = reply.get("message", reply.get("reason"))
    if not profile["enabled"] or not isinstance(value, str):
        return ""
    return value.strip()[:480]


def list_models(provider, key):
    headers = {"Authorization": f"Bearer {key}"}
    base = "https://api.deepseek.com/models"
    parameters = {}
    if provider == "Claude":
        base = "https://api.anthropic.com/v1/models"
        parameters = {"limit": 100}
        headers["anthropic-version"] = "2026-10-21"
    models = []
    while True:
        url = base + ("?" + urlencode(parameters) if parameters else "")
        with urlopen(Request(url, headers=headers), timeout=8) as response:
            page = json.load(response)
        models.extend(item["id"] for item in page["data"]
                      if isinstance(item, dict) and isinstance(item.get("id"), str)
                      and all("text" in (item.get(field) or ("text",))
                              for field in ("input_modalities", "output_modalities")))
        cursor = page.get("last_id")
        if provider != "Claude" or not page.get("has_more") or not cursor or cursor == parameters.get("after_id"):
            return tuple(dict.fromkeys(models))
        parameters["after_id"] = cursor


def windows_credentials():
    import ctypes
    from ctypes import wintypes

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
        ]

    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return ctypes, api, Credential


def load_key(provider):
    ctypes, api, credential_type = windows_credentials()
    record = ctypes.POINTER(credential_type)()
    if not api.CredReadW(f"STS2 Launcher/{provider}", 1, 0, ctypes.byref(record)):
        code = ctypes.get_last_error()
        if code == 1168:
            return ""
        raise ctypes.WinError(code)
    try:
        value = record.contents
        return ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize).decode("utf-8")
    finally:
        api.CredFree(record)


def save_key(provider, key):
    ctypes, api, credential_type = windows_credentials()
    value = key.encode("utf-8")
    blob = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    record = credential_type(Type=1, TargetName=f"STS2 Launcher/{provider}", Persist=2,
                             CredentialBlobSize=len(value), CredentialBlob=blob, UserName=provider)
    if not api.CredWriteW(ctypes.byref(record), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def archived_messages(folder, info):
    messages = []
    for path in sorted(folder.glob("*.expression.jsonl")):
        try:
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(item, dict) and isinstance(item.get("message"), str) and item["message"].strip():
                        messages.append(item)
        except OSError:
            continue
    if messages or info.get("expression_format"):
        return messages

    try:
        with (folder / "transcript.txt").open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                match = fullmatch(r"\s*(\d+) HP\s+(\S+) \| (.*?)  -- (\S.*)", line.rstrip("\n"))
                if match:
                    step, hp, action, message = match.groups()
                    if message != "random" and not message.startswith(("(only option)", "(auto)", "(fallback:")):
                        messages.append({"step": int(step), "hp": hp, "action": action, "message": message,
                                         "name": info.get("provider")})
    except OSError:
        pass
    return messages
