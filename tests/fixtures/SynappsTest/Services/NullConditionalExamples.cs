namespace SynappsTest.Services
{
    public class NullConditionalHost
    {
        private readonly ITaskService? _service;

        public NullConditionalHost(ITaskService? service)
        {
            _service = service;
        }

        public async System.Threading.Tasks.Task RunIfPresent(System.Guid id)
        {
            await (_service?.GetTaskAsync(id) ?? System.Threading.Tasks.Task.FromResult<SynappsTest.Models.TaskItem?>(null));
        }

        public void ChainedCall()
        {
            _service?.GetTaskAsync(System.Guid.Empty)?.ToString();
        }
    }
}
