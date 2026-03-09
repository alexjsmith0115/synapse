namespace SynapseTest;

public abstract class Animal : IAnimal
{
    public string Name { get; set; }
    protected readonly string _species;

    protected Animal(string name, string species)
    {
        Name = name;
        _species = species;
    }

    public abstract string Speak();
}
