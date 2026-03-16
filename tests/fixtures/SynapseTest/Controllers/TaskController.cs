namespace SynapseTest.Controllers;

using Microsoft.AspNetCore.Mvc;
using SynapseTest.Models;
using SynapseTest.Services;

[ApiController]
[Route("api/[controller]")]
public class TaskController : BaseController
{
    private readonly ITaskService _taskService;

    public TaskController(ITaskService taskService)
    {
        _taskService = taskService;
    }

    [HttpPost]
    public Task<TaskItem> Create(string title, Guid projectId)
    {
        return _taskService.CreateTaskAsync(title, projectId);
    }

    [HttpGet("{id}")]
    public Task<TaskItem?> Get(Guid id)
    {
        return _taskService.GetTaskAsync(id);
    }

    [HttpGet]
    public Task<List<TaskItem>> List(Guid projectId)
    {
        return _taskService.ListTasksAsync(projectId);
    }

    [HttpPut("{id}")]
    public Task<TaskItem> Update(Guid id, string title)
    {
        return _taskService.UpdateTaskAsync(id, title);
    }

    [HttpDelete("{id}")]
    public Task Delete(Guid id)
    {
        return _taskService.DeleteTaskAsync(id);
    }

    [HttpPost("{id}/complete")]
    public Task<TaskItem> Complete(Guid id)
    {
        return _taskService.CompleteTaskAsync(id);
    }
}
