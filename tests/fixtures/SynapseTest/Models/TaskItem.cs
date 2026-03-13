namespace SynapseTest.Models;

public class TaskItem : BaseEntity
{
    public string Title { get; set; } = "";
    public bool IsComplete { get; set; }
    public Guid ProjectId { get; set; }
    public Project? Project { get; set; }
}
