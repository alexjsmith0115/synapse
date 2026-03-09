namespace SynapseTest;

public class Cat : Animal
{
    public Cat(string name) : base(name, "Felis catus") { }

    public override string Speak() => "Meow!";
}
