using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

if (args.Length != 2)
{
    Console.Error.WriteLine("usage: Elmos.Dotnet.SemanticCli <source> <function>");
    return 2;
}

var sourcePath = Path.GetFullPath(args[0]);
var functionName = args[1];
var source = await File.ReadAllTextAsync(sourcePath);
var tree = CSharpSyntaxTree.ParseText(
    source,
    new CSharpParseOptions(LanguageVersion.CSharp14),
    Path.GetFileName(sourcePath));
var root = await tree.GetRootAsync();
var diagnostics = tree.GetDiagnostics()
    .Where(item => item.Severity == DiagnosticSeverity.Error)
    .Select(item => $"{item.Id}:{item.Location.GetLineSpan().StartLinePosition.Line + 1}")
    .Order(StringComparer.Ordinal)
    .ToList();
var functions = root.DescendantNodes()
    .OfType<MethodDeclarationSyntax>()
    .Where(item => item.Identifier.ValueText == functionName)
    .Select(SemanticMapper.Function)
    .ToList();
if (functions.Count == 0) diagnostics.Add($"FUNCTION_NOT_FOUND:{functionName}");

var output = new Dictionary<string, object?>
{
    ["schema_version"] = "1.0.0",
    ["source_language"] = "csharp",
    ["source_file"] = Path.GetFileName(sourcePath),
    ["analyzer"] = "Microsoft.CodeAnalysis.CSharp",
    ["analyzer_version"] = typeof(CSharpSyntaxTree).Assembly.GetName().Version?.ToString() ?? "unknown",
    ["functions"] = functions,
    ["diagnostics"] = diagnostics,
};
Console.WriteLine(JsonSerializer.Serialize(output));
return 0;

internal static class SemanticMapper
{
    internal static Dictionary<string, object?> Function(MethodDeclarationSyntax method)
    {
        if (method.Body is null) throw new InvalidOperationException("CSHARP_BLOCK_BODY_REQUIRED");
        return new()
        {
            ["name"] = method.Identifier.ValueText,
            ["parameters"] = method.ParameterList.Parameters.Select(parameter => new Dictionary<string, object?>
            {
                ["name"] = parameter.Identifier.ValueText,
                ["type"] = Type(parameter.Type?.ToString() ?? ""),
            }).ToList(),
            ["return_type"] = Type(method.ReturnType.ToString()),
            ["body"] = Statements(method.Body.Statements),
        };
    }

    private static string Type(string sourceType) => sourceType.Replace("System.", "", StringComparison.Ordinal) switch
    {
        "byte" or "short" or "int" or "long" or "Byte" or "Int16" or "Int32" or "Int64" => "integer",
        "float" or "double" or "decimal" or "Single" or "Double" or "Decimal" => "number",
        "bool" or "Boolean" => "boolean",
        "string" or "String" => "string",
        _ => throw new InvalidOperationException($"CSHARP_UNSUPPORTED_TYPE:{sourceType}"),
    };

    private static List<Dictionary<string, object?>> Statements(SyntaxList<StatementSyntax> statements)
    {
        var result = new List<Dictionary<string, object?>>();
        foreach (var statement in statements)
        {
            switch (statement)
            {
                case ReturnStatementSyntax returning when returning.Expression is not null:
                    result.Add(new()
                    {
                        ["kind"] = "return",
                        ["expression"] = Expression(returning.Expression),
                    });
                    break;
                case IfStatementSyntax conditional:
                    result.Add(new()
                    {
                        ["kind"] = "if",
                        ["condition"] = Expression(conditional.Condition),
                        ["then"] = StatementBody(conditional.Statement),
                        ["else"] = conditional.Else is null
                            ? new List<Dictionary<string, object?>>()
                            : StatementBody(conditional.Else.Statement),
                    });
                    break;
                default:
                    throw new InvalidOperationException($"CSHARP_UNSUPPORTED_STATEMENT:{statement.Kind()}");
            }
        }
        return result;
    }

    private static List<Dictionary<string, object?>> StatementBody(StatementSyntax statement) =>
        statement is BlockSyntax block
            ? Statements(block.Statements)
            : Statements(SyntaxFactory.SingletonList(statement));

    private static Dictionary<string, object?> Expression(ExpressionSyntax expression)
    {
        if (expression is ParenthesizedExpressionSyntax parenthesized) return Expression(parenthesized.Expression);
        if (expression is IdentifierNameSyntax identifier)
        {
            return new() { ["kind"] = "name", ["value"] = identifier.Identifier.ValueText };
        }
        if (expression is LiteralExpressionSyntax literal)
        {
            return new() { ["kind"] = "literal", ["value"] = literal.Token.Value };
        }
        if (expression is BinaryExpressionSyntax binary)
        {
            return new()
            {
                ["kind"] = "binary",
                ["operator"] = Operator(binary.Kind()),
                ["left"] = Expression(binary.Left),
                ["right"] = Expression(binary.Right),
            };
        }
        throw new InvalidOperationException($"CSHARP_UNSUPPORTED_EXPRESSION:{expression.Kind()}");
    }

    private static string Operator(SyntaxKind kind) => kind switch
    {
        SyntaxKind.AddExpression => "+",
        SyntaxKind.SubtractExpression => "-",
        SyntaxKind.MultiplyExpression => "*",
        SyntaxKind.DivideExpression => "/",
        SyntaxKind.ModuloExpression => "%",
        SyntaxKind.LessThanExpression => "<",
        SyntaxKind.LessThanOrEqualExpression => "<=",
        SyntaxKind.GreaterThanExpression => ">",
        SyntaxKind.GreaterThanOrEqualExpression => ">=",
        SyntaxKind.EqualsExpression => "==",
        SyntaxKind.NotEqualsExpression => "!=",
        SyntaxKind.LogicalAndExpression => "&&",
        SyntaxKind.LogicalOrExpression => "||",
        _ => throw new InvalidOperationException($"CSHARP_UNSUPPORTED_OPERATOR:{kind}"),
    };
}
