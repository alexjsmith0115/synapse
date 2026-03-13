namespace SynapseTest.Services;

using SynapseTest.Models;

public class ProjectService : IProjectService
{
    public Task<Project> GetProjectAsync(Guid id)
    {
        return Task.FromResult(new Project { Id = id, Name = "Default" });
    }

    public Task ValidateProjectAsync(Guid id)
    {
        GetProjectAsync(id);
        return Task.CompletedTask;
    }
}
