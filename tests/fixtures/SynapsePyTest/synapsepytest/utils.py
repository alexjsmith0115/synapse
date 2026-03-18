"""Utility helpers for the SynapsePyTest fixture."""
from synapsepytest.animals import Dog


def format_name(name: str) -> str:
    return name.strip().title()


def create_dog_greeting() -> str:
    dog = Dog()
    sound: str = dog.speak()
    name: str = format_name(dog.name)
    return f"{name}: {sound}"
