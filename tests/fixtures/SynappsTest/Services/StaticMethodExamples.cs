namespace SynappsTest.Services;

public class MathHelper
{
    public static int Add(int a, int b)
    {
        return a + b;
    }
}

public class StringHelper
{
    public static string FormatName(string first, string last)
    {
        return $"{first} {last}";
    }
}

public class StaticMethodCaller
{
    public int UseAdd()
    {
        return MathHelper.Add(1, 2);
    }

    public string UseFormat()
    {
        return StringHelper.FormatName("a", "b");
    }
}
