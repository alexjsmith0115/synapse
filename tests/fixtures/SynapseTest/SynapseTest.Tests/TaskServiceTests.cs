namespace SynapseTest.Tests;

using SynapseTest.Services;

public class TaskServiceTests
{
    private readonly ITaskService _mockService;
    private readonly TaskService _realService;

    public TaskServiceTests(ITaskService mockService, TaskService realService)
    {
        _mockService = mockService;
        _realService = realService;
    }

    public void TestCreateTask()
    {
        _mockService.CreateTaskAsync("test", Guid.NewGuid());
    }

    public void TestCompleteTask()
    {
        _mockService.CompleteTaskAsync(Guid.NewGuid());
    }
}
