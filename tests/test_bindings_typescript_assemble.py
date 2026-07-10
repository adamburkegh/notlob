"""Tests for the TypeScript code assembler."""

from __future__ import annotations


from notlob import from_tree, parse
from notlob.bindings.typescript.assemble import assemble


def assembled(source: str) -> str:
    return assemble(from_tree(parse(source)))


class TestEmpty:
    def test_no_code(self):
        assert assembled('#T\nJust prose.\n') == ''

    def test_claims_not_included(self):
        assert assembled('#T\n~example\n    a === b\n') == ''


class TestLocationComments:
    def test_module_comment(self):
        src = '#My Module\n\n    const x = 1\n'
        result = assembled(src)
        assert result.startswith('// my/module')

    def test_subheading_comment(self):
        src = '#My Module\n\n##Data\n\n    const x = 1\n'
        result = assembled(src)
        assert '// my/module#Data' in result

    def test_comment_uses_double_slash(self):
        src = '#T\n\n    const x = 1\n'
        assert assembled(src).startswith('//')

    def test_comment_not_hash(self):
        src = '#T\n\n    const x = 1\n'
        assert not assembled(src).startswith('#')


class TestReferences:
    def test_import_included(self):
        src = '#T\n---\n#References\n    import fs from "fs"\n'
        assert 'import fs from "fs"' in assembled(src)

    def test_lob_ref_dropped(self):
        src = '#T\n    const x = 1\n---\n#References\n    #Other Module\n'
        assert '#Other Module' not in assembled(src)

    def test_lob_ref_with_real_import(self):
        src = (
            '#T\n    const x = 1\n---\n#References\n'
            '    #Other Module\n'
            '    import fs from "fs"\n'
        )
        result = assembled(src)
        assert 'import fs from "fs"' in result
        assert '#Other Module' not in result


class TestCodeBlocks:
    def test_single_block(self):
        src = '#T\n\n    const x = 1\n'
        assert 'const x = 1' in assembled(src)

    def test_dedented(self):
        src = '#T\n\n    const x = 1\n    const y = 2\n'
        result = assembled(src)
        assert 'const x = 1\nconst y = 2' in result

    def test_multiple_subheadings(self):
        src = (
            '#T\n\n##A\n\n    const a = 1\n'
            '\n##B\n\n    const b = 2\n'
        )
        result = assembled(src)
        assert '// t#A\nconst a = 1' in result
        assert '// t#B\nconst b = 2' in result
