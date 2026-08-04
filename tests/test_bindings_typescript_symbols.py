"""Tests for the TypeScript symbol extractor."""

from __future__ import annotations


from notlob.bindings.typescript.symbols import extract_calls, extract_symbols


def names(lines):
    return [s.name for s in extract_symbols(lines)]


def syms(lines):
    return extract_symbols(lines)


class TestFunctions:
    def test_function_declaration(self):
        assert names(['    function foo() {}']) == ['foo']

    def test_async_function(self):
        assert names(['    async function bar() {}']) == ['bar']

    def test_generator(self):
        assert names(['    function* gen() {}']) == ['gen']

    def test_exported_function(self):
        assert names(['    export function baz() {}']) == ['baz']

    def test_export_default_function(self):
        assert names(['    export default function qux() {}']) == ['qux']


class TestVariables:
    def test_const(self):
        assert names(['    const AXES = []']) == ['AXES']

    def test_let(self):
        assert names(['    let count = 0']) == ['count']

    def test_var(self):
        assert names(['    var old = true']) == ['old']

    def test_exported_const(self):
        assert names(['    export const VALUE = 42']) == ['VALUE']

    def test_arrow_via_const(self):
        assert names(['    const fn = () => 1']) == ['fn']


class TestClasses:
    def test_class(self):
        assert names(['    class Foo {}']) == ['Foo']

    def test_abstract_class(self):
        assert names(['    abstract class Bar {}']) == ['Bar']

    def test_exported_class(self):
        assert names(['    export class Baz {}']) == ['Baz']


class TestTypesAndInterfaces:
    def test_interface(self):
        assert names(['    interface Axis {}']) == ['Axis']

    def test_type_alias(self):
        assert names(['    type Color = string']) == ['Color']

    def test_generic_type(self):
        assert names(['    type Pair<T> = [T, T]']) == ['Pair']

    def test_enum(self):
        assert names(['    enum Direction { Up, Down }']) == ['Direction']

    def test_const_enum(self):
        assert names(['    const enum Status { Ok, Err }']) == ['Status']


class TestMultipleLines:
    def test_multiple_declarations(self):
        lines = [
            '    function dist() {}',
            '    const MEDIA = []',
            '    interface Item {}',
        ]
        assert names(lines) == ['dist', 'MEDIA', 'Item']

    def test_nested_not_extracted(self):
        lines = [
            '    function outer() {',
            '        function inner() {}',
            '    }',
        ]
        # 'inner' is indented inside a block, not at column 0 after dedent
        assert names(lines) == ['outer']

    def test_empty_lines_ignored(self):
        lines = ['    ', '    const x = 1', '    ']
        assert names(lines) == ['x']


# ── Source capture ───────────────────────────────────────────

class TestSource:
    def test_single_line_declaration_has_source(self):
        result = syms(['    const AXES = []'])
        assert result[0].source == 'const AXES = []'

    def test_function_body_included_in_source(self):
        lines = [
            '    function dist(a, b) {',
            '        return a + b;',
            '    }',
        ]
        result = syms(lines)
        assert result[0].name == 'dist'
        assert 'return a + b' in result[0].source

    def test_source_split_between_declarations(self):
        lines = [
            '    function f() { return 1; }',
            '    function g() { return 2; }',
        ]
        result = syms(lines)
        assert 'return 1' in result[0].source
        assert 'return 1' not in result[1].source
        assert 'return 2' in result[1].source

    def test_nested_function_in_source_not_extracted(self):
        lines = [
            '    function outer() {',
            '        function inner() {}',
            '    }',
        ]
        result = syms(lines)
        assert len(result) == 1
        assert 'inner' in result[0].source


def _call_names(calls):
    return [n for n, _ in calls]


# ── extract_calls ────────────────────────────────────────────

class TestExtractCalls:
    def test_bare_function_call(self):
        assert "toRoman" in _call_names(extract_calls("const x = toRoman(n);"))

    def test_multiple_calls(self):
        names = _call_names(extract_calls("const x = encode(decode(s));"))
        assert "encode" in names
        assert "decode" in names

    def test_method_call_excluded(self):
        assert "toRoman" not in _call_names(extract_calls("obj.toRoman(n);"))

    def test_excludes_defined_name(self):
        src = "function toRoman(n: number) { return helper(n); }"
        names = _call_names(extract_calls(src))
        assert "toRoman" not in names
        assert "helper" in names

    def test_excludes_ts_keywords(self):
        src = "const x = new MyClass();"
        assert "new" not in _call_names(extract_calls(src))

    def test_empty_source_returns_empty(self):
        assert extract_calls("") == []

    def test_chained_call_captures_first(self):
        names = _call_names(extract_calls("const r = foo(bar(x));"))
        assert "foo" in names
        assert "bar" in names

    def test_returns_line_numbers(self):
        src = "function f() {\n  g();\n}\nfunction f2() {\n  h();\n}"
        pairs = dict(extract_calls(src))
        assert pairs["g"] == 2
        assert pairs["h"] == 5

    def test_first_occurrence_wins(self):
        src = "function f() { g(); }\nfunction f2() { g(); }"
        pairs = dict(extract_calls(src))
        assert pairs["g"] == 1
