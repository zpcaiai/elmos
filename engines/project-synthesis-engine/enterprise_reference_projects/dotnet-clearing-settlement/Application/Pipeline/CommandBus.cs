namespace Elmos.ClearingSettlement.Application.Pipeline;

using System;
using System.Collections.Concurrent;
using System.Threading.Tasks;

public interface ICommand<TResult> { }

public interface ICommandHandler<in TCommand, TResult> where TCommand : ICommand<TResult>
{
    Task<TResult> HandleAsync(TCommand command);
}

public interface ICommandBus
{
    void RegisterHandler<TCommand, TResult>(ICommandHandler<TCommand, TResult> handler) where TCommand : ICommand<TResult>;
    Task<TResult> SendAsync<TResult>(ICommand<TResult> command);
}

public sealed class CommandBus : ICommandBus
{
    private readonly ConcurrentDictionary<Type, object> _handlers = new();

    public void RegisterHandler<TCommand, TResult>(ICommandHandler<TCommand, TResult> handler) where TCommand : ICommand<TResult>
    {
        _handlers[typeof(TCommand)] = handler;
    }

    public async Task<TResult> SendAsync<TResult>(ICommand<TResult> command)
    {
        if (command == null) throw new ArgumentNullException(nameof(command));

        var commandType = command.GetType();
        if (!_handlers.TryGetValue(commandType, out var handlerObj))
        {
            throw new InvalidOperationException($"No command handler registered for {commandType.Name}");
        }

        var handler = (ICommandHandler<ICommand<TResult>, TResult>)handlerObj;
        return await handler.HandleAsync(command);
    }
}
