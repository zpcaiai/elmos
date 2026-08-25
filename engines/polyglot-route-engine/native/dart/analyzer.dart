// Copyright (c) ELMOS contributors.
//
// Dart/Flutter frontend for the bounded typed-pure-module route profile.
// Parsing is exclusively performed by package:analyzer's Dart AST. This file
// walks that AST and deliberately rejects every construct the route IR cannot
// represent; it is not a text scanner and it never approximates Widget/UI
// semantics as a pure function.

import 'dart:convert';
import 'dart:io';

import 'package:analyzer/dart/analysis/utilities.dart';
import 'package:analyzer/dart/ast/ast.dart';

const _analyzerName = 'Dart package:analyzer AST';
const _analyzerVersion = 'package:analyzer 10.1.0; Dart 3.12.1';
const _inventoryKind = 'elmos.typed-pure-module-inventory';
const _inventoryProfile = 'typed-pure-module-v1';
const _integerMin = -9223372036854775808;
const _integerMax = 9223372036854775807;

final class _DomainFailure implements Exception {
  const _DomainFailure(this.code);

  final String code;
}

Never _fail(String code) => throw _DomainFailure(code);

final class _ByteOffsets {
  _ByteOffsets(String source)
    : _prefix = List<int>.filled(source.length + 1, 0) {
    var bytes = 0;
    var index = 0;
    while (index < source.length) {
      _prefix[index] = bytes;
      final first = source.codeUnitAt(index);
      if (first >= 0xd800 && first <= 0xdbff && index + 1 < source.length) {
        final second = source.codeUnitAt(index + 1);
        if (second >= 0xdc00 && second <= 0xdfff) {
          // AST offsets never split a valid surrogate pair. Keeping a real
          // intermediate byte offset still makes a malformed boundary fail
          // safely instead of shifting every later span.
          _prefix[index + 1] = bytes + 2;
          bytes += 4;
          index += 2;
          continue;
        }
      }
      bytes += first < 0x80
          ? 1
          : first < 0x800
          ? 2
          : 3;
      index += 1;
    }
    _prefix[source.length] = bytes;
  }

  final List<int> _prefix;

  int at(int offset) {
    if (offset < 0 || offset >= _prefix.length) {
      _fail('DART_SOURCE_OFFSET_INVALID');
    }
    return _prefix[offset];
  }
}

Map<String, Object> _span(
  String fileName,
  _ByteOffsets offsets,
  AstNode node,
) => <String, Object>{
  'file': fileName,
  'start_byte': offsets.at(node.offset),
  'end_byte': offsets.at(node.end),
};

String _canonicalType(
  TypeAnnotation? annotation, {
  required String missingCode,
}) {
  if (annotation == null) _fail(missingCode);
  final spelling = annotation.toSource();
  return switch (spelling) {
    'int' => 'integer',
    'double' => 'number',
    'bool' => 'boolean',
    'String' => 'string',
    _ => _fail('DART_UNSUPPORTED_TYPE:$spelling'),
  };
}

final class _TypedExpression {
  const _TypedExpression(this.mapping, this.type);

  final Map<String, Object> mapping;
  final String type;
}

_TypedExpression _literal(
  Object value,
  String type,
  AstNode node,
  String fileName,
  _ByteOffsets offsets,
) => _TypedExpression(<String, Object>{
  'kind': 'literal',
  'value': value,
  'source_span': _span(fileName, offsets, node),
}, type);

_TypedExpression _expression(
  Expression node,
  Map<String, String> environment,
  String fileName,
  _ByteOffsets offsets,
  bool emittedTarget,
) {
  if (node is ParenthesizedExpression) {
    return _expression(
      node.expression,
      environment,
      fileName,
      offsets,
      emittedTarget,
    );
  }
  if (node is SimpleIdentifier) {
    final name = node.name;
    final type = environment[name];
    if (type == null) _fail('DART_UNDECLARED_NAME:$name');
    return _TypedExpression(<String, Object>{
      'kind': 'name',
      'value': name,
      'source_span': _span(fileName, offsets, node),
    }, type);
  }
  if (node is IntegerLiteral) {
    final value = node.value;
    if (value == null || value < 0 || value > _integerMax) {
      _fail('DART_INTEGER_LITERAL_OUT_OF_RANGE');
    }
    return _literal(value, 'integer', node, fileName, offsets);
  }
  if (node is DoubleLiteral) {
    final value = node.value;
    if (!value.isFinite) _fail('DART_NON_FINITE_LITERAL_UNSUPPORTED');
    return _literal(value, 'number', node, fileName, offsets);
  }
  if (node is BooleanLiteral) {
    return _literal(node.value, 'boolean', node, fileName, offsets);
  }
  if (node is SimpleStringLiteral) {
    return _literal(node.value, 'string', node, fileName, offsets);
  }
  if (node is PrefixExpression && node.operator.lexeme == '-') {
    final operand = node.operand;
    if (operand is IntegerLiteral) {
      final value = operand.value;
      if (value == null || value > _integerMax + 1) {
        _fail('DART_INTEGER_LITERAL_OUT_OF_RANGE');
      }
      final negative = -value;
      if (negative < _integerMin) _fail('DART_INTEGER_LITERAL_OUT_OF_RANGE');
      return _literal(negative, 'integer', node, fileName, offsets);
    }
    if (operand is DoubleLiteral) {
      final value = -operand.value;
      if (!value.isFinite) _fail('DART_NON_FINITE_LITERAL_UNSUPPORTED');
      return _literal(value, 'number', node, fileName, offsets);
    }
    _fail('DART_UNARY_MINUS_LITERAL_REQUIRED');
  }
  if (node is BinaryExpression) {
    final left = _expression(
      node.leftOperand,
      environment,
      fileName,
      offsets,
      emittedTarget,
    );
    final right = _expression(
      node.rightOperand,
      environment,
      fileName,
      offsets,
      emittedTarget,
    );
    final sourceOperator = node.operator.lexeme;
    final operator = sourceOperator == '~/' ? '/' : sourceOperator;
    const arithmetic = <String>{'+', '-', '*', '/', '%'};
    const ordering = <String>{'<', '<=', '>', '>='};
    const equality = <String>{'==', '!='};
    const logical = <String>{'&&', '||'};
    const numeric = <String>{'integer', 'number'};
    late final String resultType;
    if (arithmetic.contains(operator)) {
      if (operator == '+' && left.type == 'string' && right.type == 'string') {
        resultType = 'string';
      } else {
        if (!numeric.contains(left.type) || !numeric.contains(right.type)) {
          _fail(
            'DART_OPERAND_TYPE_MISMATCH:$sourceOperator:${left.type}:${right.type}',
          );
        }
        if (sourceOperator == '~/') {
          if (left.type != 'integer' || right.type != 'integer') {
            _fail('DART_TRUNCATING_DIVISION_REQUIRES_INTEGER_OPERANDS');
          }
          resultType = 'integer';
        } else if (sourceOperator == '/') {
          // Dart `/` always returns double. Two integer operands would be
          // misrepresented by canonical integer `/`; Dart's `~/` is the exact
          // truncating spelling and is mapped above.
          if (left.type == 'integer' && right.type == 'integer') {
            _fail('DART_INTEGER_TRUE_DIVISION_OUTSIDE_CERTIFIED_SUBSET');
          }
          resultType = 'number';
        } else {
          resultType = left.type == 'number' || right.type == 'number'
              ? 'number'
              : 'integer';
        }
      }
    } else if (ordering.contains(operator)) {
      if (!numeric.contains(left.type) || !numeric.contains(right.type)) {
        _fail(
          'DART_OPERAND_TYPE_MISMATCH:$operator:${left.type}:${right.type}',
        );
      }
      resultType = 'boolean';
    } else if (equality.contains(operator)) {
      if (left.type != right.type &&
          !(numeric.contains(left.type) && numeric.contains(right.type))) {
        _fail(
          'DART_OPERAND_TYPE_MISMATCH:$operator:${left.type}:${right.type}',
        );
      }
      resultType = 'boolean';
    } else if (logical.contains(operator)) {
      if (left.type != 'boolean' || right.type != 'boolean') {
        _fail(
          'DART_OPERAND_TYPE_MISMATCH:$operator:${left.type}:${right.type}',
        );
      }
      resultType = 'boolean';
    } else {
      _fail('DART_UNSUPPORTED_OPERATOR:$sourceOperator');
    }
    return _TypedExpression(<String, Object>{
      'kind': 'binary',
      'operator': operator,
      'left': left.mapping,
      'right': right.mapping,
      'source_span': _span(fileName, offsets, node),
    }, resultType);
  }
  if (emittedTarget && node is MethodInvocation) {
    final name = node.methodName.name;
    final arguments = node.argumentList.arguments;
    const checkedOperators = <String, String>{
      '_elmosCheckedAdd': '+',
      '_elmosCheckedSub': '-',
      '_elmosCheckedMul': '*',
      '_elmosCheckedDiv': '/',
      '_elmosCheckedMod': '%',
    };
    final checkedOperator = checkedOperators[name];
    if (node.target == null &&
        checkedOperator != null &&
        arguments.length == 2) {
      final left = _expression(
        arguments[0],
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      final right = _expression(
        arguments[1],
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      if (left.type != 'integer' || right.type != 'integer') {
        _fail('DART_EMITTED_CHECKED_INTEGER_CALL_TYPE_MISMATCH:$name');
      }
      return _TypedExpression(<String, Object>{
        'kind': 'binary',
        'operator': checkedOperator,
        'left': left.mapping,
        'right': right.mapping,
        'source_span': _span(fileName, offsets, node),
      }, 'integer');
    }
    if (node.target == null &&
        name == '_elmosNonZero' &&
        arguments.length == 1) {
      final value = _expression(
        arguments.single,
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      if (value.type != 'number') {
        _fail('DART_EMITTED_FLOAT_GUARD_TYPE_MISMATCH');
      }
      return value;
    }
    final target = node.target;
    if (target != null && name == 'toDouble' && arguments.isEmpty) {
      final value = _expression(
        target,
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      if (value.type != 'integer') {
        _fail('DART_EMITTED_INTEGER_WIDENING_TYPE_MISMATCH');
      }
      return _TypedExpression(value.mapping, 'number');
    }
    if (target != null && name == 'remainder' && arguments.length == 1) {
      final left = _expression(
        target,
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      final right = _expression(
        arguments.single,
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      if (left.type != 'number' || right.type != 'number') {
        _fail('DART_EMITTED_FLOAT_REMAINDER_TYPE_MISMATCH');
      }
      return _TypedExpression(<String, Object>{
        'kind': 'binary',
        'operator': '%',
        'left': left.mapping,
        'right': right.mapping,
        'source_span': _span(fileName, offsets, node),
      }, 'number');
    }
  }
  final kind = node.runtimeType.toString();
  if (kind.contains('InstanceCreation') ||
      kind.contains('MethodInvocation') ||
      kind.contains('FunctionExpressionInvocation')) {
    _fail('FLUTTER_UI_OR_EFFECTFUL_CALL_UNSUPPORTED:$kind');
  }
  _fail('DART_UNSUPPORTED_EXPRESSION:$kind');
}

List<Map<String, Object>> _statements(
  Iterable<Statement> nodes,
  Map<String, String> environment,
  String returnType,
  String fileName,
  _ByteOffsets offsets,
  bool emittedTarget,
) {
  final output = <Map<String, Object>>[];
  for (final node in nodes) {
    if (node is ReturnStatement) {
      final value = node.expression;
      if (value == null) _fail('DART_RETURN_EXPRESSION_REQUIRED');
      final lifted = _expression(
        value,
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      if (lifted.type != returnType) {
        _fail('DART_RETURN_TYPE_MISMATCH:$returnType:${lifted.type}');
      }
      output.add(<String, Object>{
        'kind': 'return',
        'expression': lifted.mapping,
        'source_span': _span(fileName, offsets, node),
      });
      continue;
    }
    if (node is IfStatement) {
      if (node.caseClause != null) _fail('DART_IF_CASE_UNSUPPORTED');
      final condition = _expression(
        node.expression,
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      if (condition.type != 'boolean') _fail('DART_CONDITION_MUST_BE_BOOLEAN');
      final thenStatement = node.thenStatement;
      if (thenStatement is! Block) _fail('DART_IF_BLOCK_BODY_REQUIRED');
      final thenBody = _statements(
        thenStatement.statements,
        Map<String, String>.of(environment),
        returnType,
        fileName,
        offsets,
        emittedTarget,
      );
      final elseStatement = node.elseStatement;
      final elseBody = elseStatement == null
          ? <Map<String, Object>>[]
          : elseStatement is Block
          ? _statements(
              elseStatement.statements,
              Map<String, String>.of(environment),
              returnType,
              fileName,
              offsets,
              emittedTarget,
            )
          : elseStatement is IfStatement
          ? _statements(
              <Statement>[elseStatement],
              Map<String, String>.of(environment),
              returnType,
              fileName,
              offsets,
              emittedTarget,
            )
          : _fail('DART_ELSE_BLOCK_BODY_REQUIRED');
      output.add(<String, Object>{
        'kind': 'if',
        'condition': condition.mapping,
        'then': thenBody,
        'else': elseBody,
        'source_span': _span(fileName, offsets, node),
      });
      continue;
    }
    if (node is VariableDeclarationStatement) {
      final variables = node.variables;
      if (!variables.isFinal || variables.isConst || variables.isLate) {
        _fail('DART_LOCAL_MUST_BE_FINAL');
      }
      if (variables.variables.length != 1)
        _fail('DART_ONE_LOCAL_PER_DECLARATION_REQUIRED');
      final declaredType = _canonicalType(
        variables.type,
        missingCode: 'DART_EXPLICIT_LOCAL_TYPE_REQUIRED',
      );
      final variable = variables.variables.single;
      final name = variable.name.lexeme;
      if (environment.containsKey(name))
        _fail('DART_LOCAL_NAME_ALREADY_BOUND:$name');
      final initializer = variable.initializer;
      if (initializer == null) _fail('DART_LOCAL_INITIALIZER_REQUIRED');
      final lifted = _expression(
        initializer,
        environment,
        fileName,
        offsets,
        emittedTarget,
      );
      if (lifted.type != declaredType) {
        _fail('DART_LOCAL_TYPE_MISMATCH:$declaredType:${lifted.type}');
      }
      output.add(<String, Object>{
        'kind': 'let',
        'name': name,
        'type': declaredType,
        'expression': lifted.mapping,
        'source_span': _span(fileName, offsets, node),
      });
      environment[name] = declaredType;
      continue;
    }
    _fail('DART_UNSUPPORTED_STATEMENT:${node.runtimeType}');
  }
  return output;
}

Map<String, Object> _analyzeFunction(
  FunctionDeclaration declaration,
  String fileName,
  _ByteOffsets offsets, {
  bool emittedTarget = false,
}) {
  if (declaration.externalKeyword != null ||
      declaration.augmentKeyword != null) {
    _fail('DART_EXTERNAL_OR_AUGMENT_FUNCTION_UNSUPPORTED');
  }
  if (declaration.isGetter ||
      declaration.isSetter ||
      declaration.propertyKeyword != null) {
    _fail('DART_PROPERTY_FUNCTION_UNSUPPORTED');
  }
  if (declaration.metadata.isNotEmpty)
    _fail('DART_FUNCTION_ANNOTATION_UNSUPPORTED');
  final expression = declaration.functionExpression;
  if (expression.typeParameters != null)
    _fail('DART_GENERIC_FUNCTION_UNSUPPORTED');
  final body = expression.body;
  if (body is! BlockFunctionBody) _fail('DART_BLOCK_BODY_REQUIRED');
  if (body.isAsynchronous ||
      body.isGenerator ||
      body.keyword != null ||
      body.star != null) {
    _fail('DART_ASYNC_OR_GENERATOR_FUNCTION_UNSUPPORTED');
  }
  final parameters = expression.parameters;
  if (parameters == null) _fail('DART_PARAMETER_LIST_REQUIRED');
  final environment = <String, String>{};
  final liftedParameters = <Map<String, Object>>[];
  for (final parameter in parameters.parameters) {
    if (parameter is! SimpleFormalParameter ||
        !parameter.isRequiredPositional ||
        parameter.metadata.isNotEmpty ||
        parameter.covariantKeyword != null ||
        parameter.requiredKeyword != null ||
        parameter.keyword != null) {
      _fail('DART_PARAMETER_SHAPE_UNSUPPORTED');
    }
    final nameToken = parameter.name;
    if (nameToken == null) _fail('DART_PARAMETER_NAME_REQUIRED');
    final name = nameToken.lexeme;
    if (environment.containsKey(name)) _fail('DART_DUPLICATE_PARAMETER:$name');
    final type = _canonicalType(
      parameter.type,
      missingCode: 'DART_EXPLICIT_PARAMETER_TYPE_REQUIRED',
    );
    environment[name] = type;
    liftedParameters.add(<String, Object>{
      'name': name,
      'type': type,
      'source_span': _span(fileName, offsets, parameter),
    });
  }
  final returnType = _canonicalType(
    declaration.returnType,
    missingCode: 'DART_EXPLICIT_RETURN_TYPE_REQUIRED',
  );
  final liftedBody = _statements(
    body.block.statements,
    environment,
    returnType,
    fileName,
    offsets,
    emittedTarget,
  );
  if (liftedBody.isEmpty) _fail('DART_FUNCTION_BODY_EMPTY');
  return <String, Object>{
    'name': declaration.name.lexeme,
    'parameters': liftedParameters,
    'return_type': returnType,
    'body': liftedBody,
    'source_span': _span(fileName, offsets, declaration),
  };
}

bool _isFlutterUri(String uri) =>
    uri == 'dart:ui' || uri.startsWith('package:flutter/');

void _guardPureModule(CompilationUnit unit) {
  if (unit.scriptTag != null) _fail('DART_SCRIPT_TAG_UNSUPPORTED');
  if (unit.languageVersionToken != null)
    _fail('DART_LANGUAGE_VERSION_OVERRIDE_UNSUPPORTED');
  for (final directive in unit.directives) {
    if (directive is ImportDirective) {
      final uri = directive.uri.stringValue ?? '';
      if (_isFlutterUri(uri)) _fail('FLUTTER_UI_SEMANTICS_UNSUPPORTED:$uri');
    }
    _fail('DART_DIRECTIVE_UNSUPPORTED:${directive.runtimeType}');
  }
  for (final declaration in unit.declarations) {
    if (declaration is FunctionDeclaration) continue;
    if (declaration is ClassDeclaration) {
      final parent = declaration.extendsClause?.superclass.toSource() ?? '';
      if (const <String>{
        'Widget',
        'StatelessWidget',
        'StatefulWidget',
        'State',
      }.contains(parent)) {
        _fail('FLUTTER_UI_SEMANTICS_UNSUPPORTED:$parent');
      }
    }
    _fail('DART_MODULE_DECLARATION_UNSUPPORTED:${declaration.runtimeType}');
  }
}

Map<String, Object> _semanticIr(
  CompilationUnit unit,
  String functionName,
  String fileName,
  _ByteOffsets offsets,
  bool emittedTarget,
) {
  _guardPureModule(unit);
  final candidates = unit.declarations
      .whereType<FunctionDeclaration>()
      .where((declaration) => declaration.name.lexeme == functionName)
      .toList(growable: false);
  if (candidates.length != 1) _fail('FUNCTION_NOT_FOUND:$functionName');
  return <String, Object>{
    'schema_version': '1.0.0',
    'source_language': 'flutter',
    'source_file': fileName,
    'analyzer': _analyzerName,
    'analyzer_version': _analyzerVersion,
    'functions': <Map<String, Object>>[
      _analyzeFunction(
        candidates.single,
        fileName,
        offsets,
        emittedTarget: emittedTarget,
      ),
    ],
    'diagnostics': <String>[],
  };
}

Map<String, Object> _inventorySubject(
  AstNode node,
  String fileName,
  _ByteOffsets offsets,
  bool emittedTarget,
) {
  if (node is FunctionDeclaration) {
    var analyzable = true;
    Map<String, Object> signature = <String, Object>{};
    try {
      final lifted = _analyzeFunction(
        node,
        fileName,
        offsets,
        emittedTarget: emittedTarget,
      );
      signature = <String, Object>{
        'parameters': lifted['parameters'] as Object,
        'source_return_type': node.returnType?.toSource() ?? '',
      };
    } on _DomainFailure {
      analyzable = false;
      signature = <String, Object>{
        'parameters': <Object>[],
        'source_return_type': node.returnType?.toSource() ?? '',
      };
    }
    return <String, Object>{
      'name': node.name.lexeme,
      'qualified_name': node.name.lexeme,
      'declaration_kind': 'function',
      'analyzable': analyzable,
      'source_span': _span(fileName, offsets, node),
      'signature': <String, Object>{
        ...signature,
        'visibility': node.name.lexeme.startsWith('_') ? 'private' : 'external',
        'storage': 'file-scope',
      },
    };
  }
  if (node is ImportDirective) {
    final name = node.uri.stringValue ?? '<invalid-import>';
    return <String, Object>{
      'name': name,
      'qualified_name': name,
      'declaration_kind': _isFlutterUri(name) ? 'flutter-ui-import' : 'import',
      'analyzable': false,
      'source_span': _span(fileName, offsets, node),
      'signature': <String, Object>{'uri': name},
    };
  }
  final name = node is ClassDeclaration
      ? node.name.lexeme
      : '<unsupported@${node.offset}>';
  return <String, Object>{
    'name': name,
    'qualified_name': name,
    'declaration_kind': node is ClassDeclaration
        ? 'type'
        : node.runtimeType.toString(),
    'analyzable': false,
    'source_span': _span(fileName, offsets, node),
    'signature': <String, Object>{},
  };
}

Map<String, Object> _inventory(
  CompilationUnit unit,
  String fileName,
  _ByteOffsets offsets,
  bool emittedTarget,
) {
  final subjects = <Map<String, Object>>[];
  final occurrences = <String, int>{};
  void appendSubject(AstNode node) {
    final subject = _inventorySubject(node, fileName, offsets, emittedTarget);
    final qualifiedName = subject['qualified_name']! as String;
    final occurrence = (occurrences[qualifiedName] ?? 0) + 1;
    occurrences[qualifiedName] = occurrence;
    subject['occurrence'] = occurrence;
    subjects.add(subject);
  }

  for (final directive in unit.directives) {
    appendSubject(directive);
  }
  for (final declaration in unit.declarations) {
    appendSubject(declaration);
  }
  return <String, Object>{
    'schema_version': '1.0.0',
    'kind': _inventoryKind,
    'profile': _inventoryProfile,
    'source_language': 'flutter',
    'source_file': fileName,
    'analyzer': _analyzerName,
    'analyzer_version': _analyzerVersion,
    'enumeration_status': 'PASSED',
    'subjects': subjects,
    'diagnostics': <String>[],
    'directives': <Object>[],
  };
}

void main(List<String> arguments) {
  try {
    if (arguments.length < 2 || arguments.length > 3) {
      _fail('DART_ANALYZER_COMMAND_SHAPE_INVALID');
    }
    final sourcePath = arguments[0];
    final selector = arguments[1];
    final emittedTarget =
        arguments.length == 3 && arguments[2] == '--emitted-target';
    if (arguments.length == 3 && !emittedTarget)
      _fail('DART_ANALYZER_COMMAND_SHAPE_INVALID');
    final sourceFile = File(sourcePath);
    final source = sourceFile.readAsStringSync();
    final parsed = parseString(
      content: source,
      path: sourcePath,
      throwIfDiagnostics: false,
    );
    if (parsed.errors.isNotEmpty) {
      final codes =
          parsed.errors
              .map((error) => error.diagnosticCode.name)
              .toSet()
              .toList()
            ..sort();
      _fail('DART_PARSE_FAILED:${codes.join(',')}');
    }
    final fileName = sourceFile.uri.pathSegments.last;
    final offsets = _ByteOffsets(source);
    final value = selector == '--inventory'
        ? _inventory(parsed.unit, fileName, offsets, emittedTarget)
        : _semanticIr(parsed.unit, selector, fileName, offsets, emittedTarget);
    stdout.write(jsonEncode(value));
  } on _DomainFailure catch (failure) {
    stderr.writeln(failure.code);
    exitCode = 2;
  } on FileSystemException {
    stderr.writeln('DART_SOURCE_READ_FAILED');
    exitCode = 2;
  } catch (error) {
    stderr.writeln('DART_ANALYZER_INTERNAL_FAILURE:${error.runtimeType}');
    exitCode = 2;
  }
}
