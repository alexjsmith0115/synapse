namespace SynapseTest.Controllers;

public abstract class BaseController
{
    protected Guid GetUserId()
    {
        return Guid.NewGuid();
    }

    protected Guid ConvertToGuid(string value)
    {
        return Guid.Parse(value);
    }
}
