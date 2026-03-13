namespace SynapseTest.Models;

public abstract class BaseEntity
{
    public Guid Id { get; set; }
    public DateTime CreatedAt { get; set; }
    protected string _createdBy = "";
}
