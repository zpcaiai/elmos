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
List<Dictionary<string, object?>> functions = new();
try
{
    functions = root.DescendantNodes()
        .OfType<MethodDeclarationSyntax>()
        .Where(item => item.Identifier.ValueText == functionName)
        .Select(SemanticMapper.Function)
        .ToList();
    if (functions.Count == 0) diagnostics.Add($"FUNCTION_NOT_FOUND:{functionName}");
}
catch (Exception ex)
{
    diagnostics.Add(ex.Message);
}

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
        var paramNames = method.ParameterList.Parameters.Select(p => p.Identifier.ValueText).ToHashSet();
        var scopeVars = new Dictionary<string, string>();
        foreach (var p in method.ParameterList.Parameters)
        {
            scopeVars[p.Identifier.ValueText] = Type(p.Type?.ToString() ?? "");
        }
        return new()
        {
            ["name"] = method.Identifier.ValueText,
            ["parameters"] = method.ParameterList.Parameters.Select(parameter => new Dictionary<string, object?>
            {
                ["name"] = parameter.Identifier.ValueText,
                ["type"] = Type(parameter.Type?.ToString() ?? ""),
            }).ToList(),
            ["return_type"] = Type(method.ReturnType.ToString()),
            ["body"] = Statements(method.Body.Statements, scopeVars, paramNames),
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

    private static List<Dictionary<string, object?>> Statements(
        SyntaxList<StatementSyntax> statements,
        Dictionary<string, string> scopeVars,
        HashSet<string> paramNames)
    {
        var result = new List<Dictionary<string, object?>>();
        foreach (var statement in statements)
        {
            switch (statement)
            {
                case LocalDeclarationStatementSyntax localDecl:
                {
                    if (localDecl.Declaration.Type.IsVar)
                    {
                        throw new InvalidOperationException("CSHARP_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET");
                    }
                    var declaredType = Type(localDecl.Declaration.Type.ToString());
                    foreach (var variable in localDecl.Declaration.Variables)
                    {
                        if (variable.Initializer is null)
                        {
                            throw new InvalidOperationException("CSHARP_ANNOTATED_DECLARATION_WITHOUT_VALUE");
                        }
                        var varName = variable.Identifier.ValueText;
                        var valExpr = Expression(variable.Initializer.Value);
                        scopeVars[varName] = declaredType;
                        result.Add(new()
                        {
                            ["kind"] = "let",
                            ["name"] = varName,
                            ["type"] = declaredType,
                            ["expression"] = valExpr,
                        });
                    }
                    break;
                }
                case ExpressionStatementSyntax exprStmt:
                {
                    var expr = exprStmt.Expression;
                    if (expr is AssignmentExpressionSyntax assign)
                    {
                        if (assign.Left is not IdentifierNameSyntax id)
                        {
                            throw new InvalidOperationException("CSHARP_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        var targetName = id.Identifier.ValueText;
                        if (paramNames.Contains(targetName))
                        {
                            throw new InvalidOperationException($"CSHARP_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{targetName}");
                        }
                        if (!scopeVars.ContainsKey(targetName))
                        {
                            throw new InvalidOperationException($"CSHARP_ASSIGNMENT_TARGET_NOT_DECLARED:{targetName}");
                        }
                        if (assign.Kind() == SyntaxKind.SimpleAssignmentExpression)
                        {
                            result.Add(new()
                            {
                                ["kind"] = "assign",
                                ["name"] = targetName,
                                ["expression"] = Expression(assign.Right),
                            });
                        }
                        else
                        {
                            string op = assign.Kind() switch
                            {
                                SyntaxKind.AddAssignmentExpression => "+",
                                SyntaxKind.SubtractAssignmentExpression => "-",
                                SyntaxKind.MultiplyAssignmentExpression => "*",
                                SyntaxKind.DivideAssignmentExpression => "/",
                                SyntaxKind.ModuloAssignmentExpression => "%",
                                _ => throw new InvalidOperationException($"CSHARP_UNSUPPORTED_OPERATOR:{assign.Kind()}"),
                            };
                            var binaryExpr = new Dictionary<string, object?>
                            {
                                ["kind"] = "binary",
                                ["operator"] = op,
                                ["left"] = new Dictionary<string, object?> { ["kind"] = "name", ["value"] = targetName },
                                ["right"] = Expression(assign.Right),
                            };
                            result.Add(new()
                            {
                                ["kind"] = "assign",
                                ["name"] = targetName,
                                ["expression"] = binaryExpr,
                            });
                        }
                    }
                    else if (expr is PostfixUnaryExpressionSyntax postUnary &&
                             (postUnary.Kind() is SyntaxKind.PostIncrementExpression or SyntaxKind.PostDecrementExpression))
                    {
                        if (postUnary.Operand is not IdentifierNameSyntax id)
                        {
                            throw new InvalidOperationException("CSHARP_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        var targetName = id.Identifier.ValueText;
                        if (paramNames.Contains(targetName))
                        {
                            throw new InvalidOperationException($"CSHARP_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{targetName}");
                        }
                        if (!scopeVars.ContainsKey(targetName))
                        {
                            throw new InvalidOperationException($"CSHARP_ASSIGNMENT_TARGET_NOT_DECLARED:{targetName}");
                        }
                        string op = postUnary.Kind() == SyntaxKind.PostIncrementExpression ? "+" : "-";
                        var binaryExpr = new Dictionary<string, object?>
                        {
                            ["kind"] = "binary",
                            ["operator"] = op,
                            ["left"] = new Dictionary<string, object?> { ["kind"] = "name", ["value"] = targetName },
                            ["right"] = new Dictionary<string, object?> { ["kind"] = "literal", ["value"] = 1L },
                        };
                        result.Add(new()
                        {
                            ["kind"] = "assign",
                            ["name"] = targetName,
                            ["expression"] = binaryExpr,
                        });
                    }
                    else if (expr is PrefixUnaryExpressionSyntax preUnary &&
                             (preUnary.Kind() is SyntaxKind.PreIncrementExpression or SyntaxKind.PreDecrementExpression))
                    {
                        if (preUnary.Operand is not IdentifierNameSyntax id)
                        {
                            throw new InvalidOperationException("CSHARP_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET");
                        }
                        var targetName = id.Identifier.ValueText;
                        if (paramNames.Contains(targetName))
                        {
                            throw new InvalidOperationException($"CSHARP_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:{targetName}");
                        }
                        if (!scopeVars.ContainsKey(targetName))
                        {
                            throw new InvalidOperationException($"CSHARP_ASSIGNMENT_TARGET_NOT_DECLARED:{targetName}");
                        }
                        string op = preUnary.Kind() == SyntaxKind.PreIncrementExpression ? "+" : "-";
                        var binaryExpr = new Dictionary<string, object?>
                        {
                            ["kind"] = "binary",
                            ["operator"] = op,
                            ["left"] = new Dictionary<string, object?> { ["kind"] = "name", ["value"] = targetName },
                            ["right"] = new Dictionary<string, object?> { ["kind"] = "literal", ["value"] = 1L },
                        };
                        result.Add(new()
                        {
                            ["kind"] = "assign",
                            ["name"] = targetName,
                            ["expression"] = binaryExpr,
                        });
                    }
                    else
                    {
                        throw new InvalidOperationException($"CSHARP_UNSUPPORTED_STATEMENT:{expr.Kind()}");
                    }
                    break;
                }
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
                        ["then"] = StatementBody(conditional.Statement, new Dictionary<string, string>(scopeVars), paramNames),
                        ["else"] = conditional.Else is null
                            ? new List<Dictionary<string, object?>>()
                            : StatementBody(conditional.Else.Statement, new Dictionary<string, string>(scopeVars), paramNames),
                    });
                    break;
                case WhileStatementSyntax whileLoop:
                    result.Add(new()
                    {
                        ["kind"] = "while",
                        ["condition"] = Expression(whileLoop.Condition),
                        ["body"] = StatementBody(whileLoop.Statement, new Dictionary<string, string>(scopeVars), paramNames),
                    });
                    break;
                case ForStatementSyntax forLoop:
                {
                    if (forLoop.Declaration is null || forLoop.Declaration.Variables.Count != 1)
                    {
                        throw new InvalidOperationException("CSHARP_FOR_INIT_OUTSIDE_CERTIFIED_SUBSET");
                    }
                    var initVar = forLoop.Declaration.Variables[0];
                    if (initVar.Initializer is null)
                    {
                        throw new InvalidOperationException("CSHARP_FOR_INIT_OUTSIDE_CERTIFIED_SUBSET");
                    }
                    if (forLoop.Declaration.Type.IsVar)
                    {
                        throw new InvalidOperationException("CSHARP_FOR_INIT_OUTSIDE_CERTIFIED_SUBSET");
                    }
                    var initType = Type(forLoop.Declaration.Type.ToString());
                    if (initType != "integer")
                    {
                        throw new InvalidOperationException("CSHARP_FOR_INIT_OUTSIDE_CERTIFIED_SUBSET");
                    }
                    var varName = initVar.Identifier.ValueText;
                    var start = Expression(initVar.Initializer.Value);

                    if (forLoop.Condition is not BinaryExpressionSyntax binCond || binCond.Kind() != SyntaxKind.LessThanExpression)
                    {
                        throw new InvalidOperationException("CSHARP_FOR_CONDITION_NON_MONOTONIC");
                    }
                    if (binCond.Left is not IdentifierNameSyntax leftId || leftId.Identifier.ValueText != varName)
                    {
                        throw new InvalidOperationException("CSHARP_FOR_CONDITION_NON_MONOTONIC");
                    }
                    var end = Expression(binCond.Right);

                    if (forLoop.Incrementors.Count != 1)
                    {
                        throw new InvalidOperationException("CSHARP_FOR_UPDATE_NON_MONOTONIC");
                    }
                    var incExpr = forLoop.Incrementors[0];
                    Dictionary<string, object?>? step = null;
                    if (incExpr is PostfixUnaryExpressionSyntax postInc && postInc.Kind() == SyntaxKind.PostIncrementExpression)
                    {
                        if (postInc.Operand is not IdentifierNameSyntax id || id.Identifier.ValueText != varName)
                        {
                            throw new InvalidOperationException("CSHARP_FOR_UPDATE_NON_MONOTONIC");
                        }
                    }
                    else if (incExpr is PrefixUnaryExpressionSyntax preInc && preInc.Kind() == SyntaxKind.PreIncrementExpression)
                    {
                        if (preInc.Operand is not IdentifierNameSyntax id || id.Identifier.ValueText != varName)
                        {
                            throw new InvalidOperationException("CSHARP_FOR_UPDATE_NON_MONOTONIC");
                        }
                    }
                    else if (incExpr is AssignmentExpressionSyntax compAssign && compAssign.Kind() == SyntaxKind.AddAssignmentExpression)
                    {
                        if (compAssign.Left is not IdentifierNameSyntax id || id.Identifier.ValueText != varName)
                        {
                            throw new InvalidOperationException("CSHARP_FOR_UPDATE_NON_MONOTONIC");
                        }
                        step = Expression(compAssign.Right);
                    }
                    else
                    {
                        throw new InvalidOperationException("CSHARP_FOR_UPDATE_NON_MONOTONIC");
                    }

                    var loopScope = new Dictionary<string, string>(scopeVars) { [varName] = "integer" };
                    var body = StatementBody(forLoop.Statement, loopScope, paramNames);

                    var item = new Dictionary<string, object?>
                    {
                        ["kind"] = "for",
                        ["name"] = varName,
                        ["type"] = "integer",
                        ["start"] = start,
                        ["end"] = end,
                        ["body"] = body,
                    };
                    if (step != null)
                    {
                        item["step"] = step;
                    }
                    result.Add(item);
                    break;
                }
                case BreakStatementSyntax:
                    result.Add(new() { ["kind"] = "break" });
                    break;
                case ContinueStatementSyntax:
                    result.Add(new() { ["kind"] = "continue" });
                    break;
                case DoStatementSyntax:
                    throw new InvalidOperationException("CSHARP_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET");
                default:
                    throw new InvalidOperationException($"CSHARP_UNSUPPORTED_STATEMENT:{statement.Kind()}");
            }
        }
        return result;
    }

    private static List<Dictionary<string, object?>> StatementBody(
        StatementSyntax statement,
        Dictionary<string, string> scopeVars,
        HashSet<string> paramNames) =>
        statement is BlockSyntax block
            ? Statements(block.Statements, scopeVars, paramNames)
            : Statements(SyntaxFactory.SingletonList(statement), scopeVars, paramNames);

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
        if (expression is PrefixUnaryExpressionSyntax unaryMinus && unaryMinus.Kind() == SyntaxKind.UnaryMinusExpression)
        {
            if (unaryMinus.Operand is LiteralExpressionSyntax numLit)
            {
                if (numLit.Token.Value is int i) return new() { ["kind"] = "literal", ["value"] = -(long)i };
                if (numLit.Token.Value is long l) return new() { ["kind"] = "literal", ["value"] = -l };
                if (numLit.Token.Value is double d) return new() { ["kind"] = "literal", ["value"] = -d };
            }
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
        if (expression is CheckedExpressionSyntax checkedExpression)
        {
            return Expression(checkedExpression.Expression);
        }
        if (expression is InvocationExpressionSyntax invocation)
        {
            if (invocation.Expression is IdentifierNameSyntax callIdent)
            {
                return new()
                {
                    ["kind"] = "call",
                    ["function"] = callIdent.Identifier.ValueText,
                    ["arguments"] = invocation.ArgumentList.Arguments.Select(a => Expression(a.Expression)).ToList(),
                };
            }
            if (invocation.Expression.ToString() == "Migrated.ElmosNonZero" && invocation.ArgumentList.Arguments.Count == 1)
            {
                return Expression(invocation.ArgumentList.Arguments[0].Expression);
            }
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
