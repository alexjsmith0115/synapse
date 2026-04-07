namespace SynappsTest.Services;

using SynappsTest.Models;

public class DelegateHost
{
    private readonly ITaskService _service;

    public DelegateHost(ITaskService service)
    {
        _service = service;
    }

    public async Task<TaskItem?> RunWithDelegate(Func<Guid, Task<TaskItem?>> fetch, Guid id)
    {
        return await fetch(id);
    }

    // Passes _service.GetTaskAsync as a method group (delegate argument).
    // VALID-02: ReferencesResolver must produce a CALLS edge from this method to GetTaskAsync.
    public async Task CallWithMethodGroup()
    {
        await RunWithDelegate(_service.GetTaskAsync, Guid.Empty);
    }
}
