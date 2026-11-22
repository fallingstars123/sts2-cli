"""Canonical character IDs shared by the desktop launcher and terminal clients."""

CHARACTERS = ("Ironclad", "Silent", "Defect", "Regent", "Necrobinder", "Fool")


def character_id(value):
    if isinstance(value, dict):
        value = value.get("en")
    if not isinstance(value, str):
        return None
    name = value.strip().casefold().removeprefix("the ")
    return next((character for character in CHARACTERS if character.casefold() == name), None)
