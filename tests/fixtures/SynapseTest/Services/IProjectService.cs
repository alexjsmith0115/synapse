namespace SynapseTest.Services;

using SynapseTest.Models;

public interface IProjectService
{
    Task<Project> GetProjectAsync(Guid id);
    Task ValidateProjectAsync(Guid id);
}
