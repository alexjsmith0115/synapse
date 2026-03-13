namespace SynapseTest.Models;

public class Project : BaseEntity
{
    public string Name { get; set; } = "";
    public ICollection<TaskItem> Tasks { get; set; } = new List<TaskItem>();
}
