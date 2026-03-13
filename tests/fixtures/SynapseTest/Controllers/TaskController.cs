namespace SynapseTest.Controllers;

using SynapseTest.Models;
using SynapseTest.Services;

public class TaskController : BaseController
{
    private readonly ITaskService _taskService;

    public TaskController(ITaskService taskService)
    {
        _taskService = taskService;
    }

    public Task<TaskItem> Create(string title, Guid projectId)
    {
        return _taskService.CreateTaskAsync(title, projectId);
    }

    public Task<TaskItem?> Get(Guid id)
    {
        return _taskService.GetTaskAsync(id);
    }

    public Task<List<TaskItem>> List(Guid projectId)
    {
        return _taskService.ListTasksAsync(projectId);
    }

    public Task<TaskItem> Update(Guid id, string title)
    {
        return _taskService.UpdateTaskAsync(id, title);
    }

    public Task Delete(Guid id)
    {
        return _taskService.DeleteTaskAsync(id);
    }

    public Task<TaskItem> Complete(Guid id)
    {
        return _taskService.CompleteTaskAsync(id);
    }
}
