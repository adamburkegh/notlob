"""Tests for the TypeScript symbol extractor."""

from __future__ import annotations

import pytest

from notlob.bindings.typescript.symbols import extract_symbols


def names(lines):
    return [s.name for s in extract_symbols(lines)]


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
