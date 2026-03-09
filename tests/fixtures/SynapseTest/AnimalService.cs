namespace SynapseTest;

public class AnimalService
{
    private readonly IAnimal _animal;

    public AnimalService(IAnimal animal)
    {
        _animal = animal;
    }

    public string MakeNoise()
    {
        return _animal.Speak();
    }
}
