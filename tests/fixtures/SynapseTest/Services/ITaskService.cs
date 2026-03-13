namespace SynapseTest.Services;

using SynapseTest.Models;

public interface ITaskService
{
    Task<TaskItem> CreateTaskAsync(string title, Guid projectId);
    Task<TaskItem?> GetTaskAsync(Guid id);
    Task<List<TaskItem>> ListTasksAsync(Guid projectId);
    Task<TaskItem> UpdateTaskAsync(Guid id, string title);
    Task DeleteTaskAsync(Guid id);
    Task<TaskItem> CompleteTaskAsync(Guid id);
}
