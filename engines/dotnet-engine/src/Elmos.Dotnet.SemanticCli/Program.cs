using System.Text.Json;
using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

if (args.Length != 2)
{
    Console.Error.WriteLine("usage: Elmos.Dotnet.SemanticCli <source> <function|--inventory>");
    return 2;
}

var sourcePath = Path.GetFullPath(args[0]);
var functionName = args[1];
var inventoryMode = functionName == "--inventory";
var source = await File.ReadAllTextAsync(sourcePath);
var tree = CSharpSyntaxTree.ParseText(
    source,
    new CSharpParseOptions(LanguageVersion.CSharp14),
    Path.GetFileName(sourcePath));
var root = (CompilationUnitSyntax)await tree.GetRootAsync();
var diagnostics = tree.GetDiagnostics()
    .Where(item => item.Severity == DiagnosticSeverity.Error)
    .Select(item => $"{item.Id}:{item.Location.GetLineSpan().StartLinePosition.Line + 1}")
    .Order(StringComparer.Ordinal)
    .ToList();
if (inventoryMode)
{
    Dictionary<string, object?> Span(SyntaxNode node) => new()
    {
        ["file"] = Path.GetFileName(sourcePath),
        ["start_byte"] = Encoding.UTF8.GetByteCount(source.AsSpan(0, node.Span.Start)),
        ["end_byte"] = Encoding.UTF8.GetByteCount(source.AsSpan(0, node.Span.End)),
    };

    string Qualified(MemberDeclarationSyntax member, string name)
    {
        var scopes = member.Ancestors()
            .OfType<BaseTypeDeclarationSyntax>()
            .Select(item => item.Identifier.ValueText)
            .Reverse();
        return string.Join(".", scopes.Append(name));
    }

    bool PlainTypeWrapper(BaseTypeDeclarationSyntax type)
    {
        if (type is not ClassDeclarationSyntax declaration) return false;
        var permittedModifiers = declaration.Modifiers.All(modifier =>
            modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.PublicKeyword)
            || modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.InternalKeyword)
            || modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.StaticKeyword));
        return declaration.Modifiers.Any(Microsoft.CodeAnalysis.CSharp.SyntaxKind.StaticKeyword)
            && permittedModifiers
            && declaration.AttributeLists.Count == 0
            && declaration.BaseList is null
            && declaration.TypeParameterList is null
            && declaration.ConstraintClauses.Count == 0
            && declaration.ParameterList is null
            && declaration.OpenBraceToken.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.OpenBraceToken)
            && declaration.CloseBraceToken.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.CloseBraceToken)
            && declaration.Members.All(member => member is MethodDeclarationSyntax);
    }

    var subjects = new List<Dictionary<string, object?>>();
    foreach (var attributeList in root.AttributeLists)
    {
        var name = attributeList.Target?.Identifier.ValueText ?? "assembly-or-module-attribute";
        subjects.Add(new()
        {
            ["name"] = $"<{name}>",
            ["qualified_name"] = $"<global-attribute:{name}>",
            ["declaration_kind"] = "GlobalAttributeList",
            ["analyzable"] = false,
            ["source_span"] = Span(attributeList),
            ["signature"] = new Dictionary<string, object?>
            {
                ["attributes"] = attributeList.Attributes.Select(item => item.Name.ToString()).ToList(),
            },
        });
    }
    foreach (var directive in root.DescendantNodes().OfType<UsingDirectiveSyntax>())
    {
        var name = directive.Name?.ToString() ?? "<using>";
        subjects.Add(new()
        {
            ["name"] = name,
            ["qualified_name"] = name,
            ["declaration_kind"] = "using",
            ["analyzable"] = false,
            ["source_span"] = Span(directive),
            ["signature"] = new Dictionary<string, object?> { ["static"] = directive.StaticKeyword.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.StaticKeyword) },
        });
    }
    foreach (var member in root.DescendantNodes().OfType<MemberDeclarationSyntax>())
    {
        string? name = member switch
        {
            MethodDeclarationSyntax method => method.Identifier.ValueText,
            ConstructorDeclarationSyntax constructor => constructor.Identifier.ValueText,
            FieldDeclarationSyntax field => string.Join(",", field.Declaration.Variables.Select(item => item.Identifier.ValueText)),
            PropertyDeclarationSyntax property => property.Identifier.ValueText,
            EventDeclarationSyntax eventDeclaration => eventDeclaration.Identifier.ValueText,
            EventFieldDeclarationSyntax eventField => string.Join(",", eventField.Declaration.Variables.Select(item => item.Identifier.ValueText)),
            DelegateDeclarationSyntax delegateDeclaration => delegateDeclaration.Identifier.ValueText,
            BaseTypeDeclarationSyntax type when type.Ancestors().OfType<BaseTypeDeclarationSyntax>().Any() => type.Identifier.ValueText,
            _ => null,
        };
        var namespaceWrapper = member is BaseNamespaceDeclarationSyntax;
        var topLevelType = member as BaseTypeDeclarationSyntax;
        var isTopLevelType = topLevelType is not null
            && !topLevelType.Ancestors().OfType<BaseTypeDeclarationSyntax>().Any();
        if (name is null && namespaceWrapper) continue;
        if (isTopLevelType && PlainTypeWrapper(topLevelType!)) continue;
        if (isTopLevelType) name = topLevelType!.Identifier.ValueText;
        name ??= $"<{member.Kind()}@{member.SpanStart}>";
        var methodDeclaration = member as MethodDeclarationSyntax;
        var permittedModifiers = methodDeclaration?.Modifiers.All(modifier =>
            modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.StaticKeyword)
            || modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.PublicKeyword)
            || modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.InternalKeyword)
            || modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.ProtectedKeyword)
            || modifier.IsKind(Microsoft.CodeAnalysis.CSharp.SyntaxKind.PrivateKeyword)) ?? false;
        var supportedParameters = methodDeclaration?.ParameterList.Parameters.All(parameter =>
            parameter.AttributeLists.Count == 0
            && parameter.Default is null
            && parameter.Modifiers.Count == 0) ?? false;
        var analyzable = methodDeclaration is not null
            && methodDeclaration.Body is not null
            && methodDeclaration.Modifiers.Any(Microsoft.CodeAnalysis.CSharp.SyntaxKind.StaticKeyword)
            && permittedModifiers
            && supportedParameters
            && methodDeclaration.AttributeLists.Count == 0
            && methodDeclaration.TypeParameterList is null
            && methodDeclaration.ConstraintClauses.Count == 0
            && methodDeclaration.ExplicitInterfaceSpecifier is null;
        var signature = methodDeclaration is null
            ? new Dictionary<string, object?> { ["source_kind"] = member.Kind().ToString() }
            : new Dictionary<string, object?>
            {
                ["parameters"] = methodDeclaration.ParameterList.Parameters.Select(parameter => new Dictionary<string, object?>
                {
                    ["name"] = parameter.Identifier.ValueText,
                    ["source_type"] = parameter.Type?.ToString() ?? "",
                }).ToList(),
                ["source_return_type"] = methodDeclaration.ReturnType.ToString(),
                ["static"] = methodDeclaration.Modifiers.Any(Microsoft.CodeAnalysis.CSharp.SyntaxKind.StaticKeyword),
            };
        subjects.Add(new()
        {
            ["name"] = name,
            ["qualified_name"] = Qualified(member, name),
            ["declaration_kind"] = member.Kind().ToString(),
            ["analyzable"] = analyzable,
            ["source_span"] = Span(member),
            ["signature"] = signature,
        });
    }
    var inventory = new Dictionary<string, object?>
    {
        ["schema_version"] = "1.0.0",
        ["kind"] = "elmos.typed-pure-module-inventory",
        ["profile"] = "typed-pure-module-v1",
        ["source_language"] = "csharp",
        ["source_file"] = Path.GetFileName(sourcePath),
        ["analyzer"] = "Microsoft.CodeAnalysis.CSharp",
        ["analyzer_version"] = typeof(CSharpSyntaxTree).Assembly.GetName().Version?.ToString() ?? "unknown",
        ["enumeration_status"] = diagnostics.Count == 0 ? "PASSED" : "FAILED",
        ["subjects"] = subjects,
        ["diagnostics"] = diagnostics,
    };
    Console.WriteLine(JsonSerializer.Serialize(inventory));
    return 0;
}
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

    // The canonical `number` is IEEE-754 binary64. `float`/`Single` has a
    // 24-bit significand and `decimal`/`Decimal` is exact base-10 with a
    // 96-bit integer scale: neither survives a round trip through binary64
    // (0.1f + 0.2f != 0.1 + 0.2, and decimal arithmetic is exact where
    // binary64 is not), so both are refused instead of silently widened.
    private static string Type(string sourceType) => sourceType.Replace("System.", "", StringComparison.Ordinal) switch
    {
        "byte" or "short" or "int" or "long" or "Byte" or "Int16" or "Int32" or "Int64" => "integer",
        "double" or "Double" => "number",
        "bool" or "Boolean" => "boolean",
        "string" or "String" => "string",
        "float" or "Single" => throw new InvalidOperationException(
            $"CSHARP_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET:{sourceType}"),
        "decimal" or "Decimal" => throw new InvalidOperationException(
            $"CSHARP_EXACT_ARITHMETIC_TYPE_OUTSIDE_CERTIFIED_SUBSET:{sourceType}"),
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
