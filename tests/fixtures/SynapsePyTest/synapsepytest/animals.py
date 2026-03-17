from abc import ABC, abstractmethod


class IAnimal(ABC):
    @abstractmethod
    def speak(self) -> str: ...

    @abstractmethod
    def name(self) -> str: ...


class Animal(IAnimal):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def speak(self) -> str:
        return "..."


class Dog(Animal):
    def __init__(self) -> None:
        super().__init__("Dog")

    def speak(self) -> str:
        return "Woof"

    def fetch(self, item: str) -> str:
        return f"Fetching {item}"


class Cat(Animal):
    def __init__(self) -> None:
        super().__init__("Cat")

    def speak(self) -> str:
        return "Meow"
