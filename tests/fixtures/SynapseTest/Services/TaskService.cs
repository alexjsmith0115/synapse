namespace SynapseTest.Services;

using SynapseTest.Models;

public class TaskService : ITaskService
{
    private readonly IProjectService _projectService;

    public TaskService(IProjectService projectService)
    {
        _projectService = projectService;
    }

    public Task<TaskItem> CreateTaskAsync(string title, Guid projectId)
    {
        // Intentionally not awaited — call site exists to generate a cross-service CALLS edge
        _projectService.ValidateProjectAsync(projectId);
        return Task.FromResult(new TaskItem { Title = title, ProjectId = projectId });
    }

    public Task<TaskItem?> GetTaskAsync(Guid id)
    {
        return Task.FromResult<TaskItem?>(new TaskItem { Id = id });
    }

    public Task<List<TaskItem>> ListTasksAsync(Guid projectId)
    {
        return Task.FromResult(new List<TaskItem>());
    }

    public Task<TaskItem> UpdateTaskAsync(Guid id, string title)
    {
        return Task.FromResult(new TaskItem { Id = id, Title = title });
    }

    public Task DeleteTaskAsync(Guid id)
    {
        return Task.CompletedTask;
    }

    public Task<TaskItem> CompleteTaskAsync(Guid id)
    {
        return Task.FromResult(new TaskItem { Id = id, IsComplete = true });
    }
}
