from synapsepytest.animals import IAnimal


class AnimalService:
    def __init__(self, animal: IAnimal) -> None:
        self._animal = animal

    def get_greeting(self) -> str:
        return f"{self._animal.name} says {self._animal.speak()}"

    @staticmethod
    def version() -> str:
        return "1.0.0"


class Greeter:
    def __init__(self, service: AnimalService) -> None:
        self._service = service

    def greet(self) -> str:
        return f"Hello! {self._service.get_greeting()}"
