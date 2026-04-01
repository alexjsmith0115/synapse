namespace SynappsTest.Endpoints;

using Microsoft.AspNetCore.Routing;

public class TodoItems : IEndpointGroup
{
    public void Map(RouteGroupBuilder app)
    {
        // Route-first: string literal as first arg
        app.MapGet("/", GetAllTodos);
        // Handler-first: identifier as first arg
        app.MapPost(CreateTodo, "/");
    }

    public static IResult GetAllTodos()
    {
        return Results.Ok(new[] { "todo1", "todo2" });
    }

    public static IResult CreateTodo()
    {
        return Results.Created("/", null);
    }
}

public class ItemGroup : EndpointGroupBase
{
    public void Map(RouteGroupBuilder app)
    {
        // Route-first: string literal as first arg
        app.MapDelete("/items/{id}", DeleteItem);
    }

    public static IResult DeleteItem()
    {
        return Results.NoContent();
    }
}
