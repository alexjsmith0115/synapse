from synapsepytest.animals import IAnimal


class AnimalService:
    def __init__(self, animal: IAnimal) -> None:
        self._animal = animal

    def get_greeting(self) -> str:
        return f"{self._animal.name} says {self._animal.speak()}"

    @staticmethod
    def version() -> str:
        return "1.0.0"

    @classmethod
    def from_name(cls, name: str) -> "AnimalService":
        from synapsepytest.animals import Animal
        return cls(Animal(name))

    async def get_greeting_async(self) -> str:
        return self.get_greeting()


class Greeter:
    def __init__(self, service: AnimalService) -> None:
        self._service = service

    def greet(self) -> str:
        return f"Hello! {self._service.get_greeting()}"
