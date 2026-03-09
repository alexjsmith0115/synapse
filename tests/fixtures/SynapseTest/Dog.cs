namespace SynapseTest;

public class Dog : Animal
{
    public Dog(string name) : base(name, "Canis lupus familiaris") { }

    public override string Speak() => "Woof!";
}
