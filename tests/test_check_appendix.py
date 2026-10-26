"""The checks that read a document's sections read the Appendix too.

An ``#Appendix`` is a section like any other: its title is one of the
titles, its bullet lists count, and its prose is checked against its
claims. The subheadings in it were always checked; the Appendix itself,
with what is written before its first subheading, was left out by how the
checks were written, not by design.
"""

from __future__ import annotations

from notlob.bindings.python.symbols import extract_symbols
from notlob.check import check_quantifier, check_style, check_titles
from notlob.project import build_package


def _package(tmp_path, source: str):
    (tmp_path / "binding.lob").write_text(
        "#P\n\n---\n\n#Binding\n    ~language python\n", encoding="utf-8")
    (tmp_path / "main.lob").write_text(source, encoding="utf-8")
    return build_package(tmp_path, extract_symbols)


class TestTitles:
    def test_an_appendix_title_is_compared_with_the_others(self, tmp_path):
        graph = _package(
            tmp_path,
            "#Main\n\n##Notes Appendix\n\nText.\n\n"
            "---\n\n#Appendix Notes\n\nMore text.\n")
        findings = check_titles(graph)
        assert [f.addresses for f in findings] == [
            ("main#Notes Appendix", "main#appendix#1")]
        assert "similar" in findings[0].message

    def test_an_unlike_appendix_title_is_not_flagged(self, tmp_path):
        graph = _package(
            tmp_path,
            "#Main\n\n##Discount Rules\n\nText.\n\n"
            "---\n\n#Appendix Notes\n\nMore text.\n")
        assert check_titles(graph) == []


class TestStyle:
    def test_the_bullet_lists_of_an_appendix_are_counted(self, tmp_path):
        graph = _package(
            tmp_path,
            "#Main\n\n    x = 1\n\n---\n\n#Appendix Notes\n\n"
            "* a\n\n* b\n")
        findings = check_style(graph)
        assert [f.addresses for f in findings] == [("main#appendix#1",)]
        assert findings[0].severity == "advisory"
        assert "2" in findings[0].message

    def test_one_bullet_list_in_an_appendix_is_fine(self, tmp_path):
        graph = _package(
            tmp_path,
            "#Main\n\n    x = 1\n\n---\n\n#Appendix Notes\n\n"
            "* a\n* b\n")
        assert check_style(graph) == []


class TestQuantifier:
    def test_the_prose_of_an_appendix_is_checked(self, tmp_path):
        graph = _package(
            tmp_path,
            "#Main\n\n    x = 1\n\n---\n\n#Appendix Notes\n\n"
            "On the turn, each token fires a randomly chosen "
            "transition.\n")
        findings = check_quantifier(graph)
        assert [f.addresses for f in findings] == [("main#appendix#1",)]
        assert "each token fires" in findings[0].message

    def test_a_claim_in_the_appendix_silences_it(self, tmp_path):
        graph = _package(
            tmp_path,
            "#Main\n\n---\n\n#Appendix Notes\n\n"
            "On the turn, each token fires a randomly chosen "
            "transition.\n\n"
            "    def f():\n        return 1\n\n"
            "~example\n    f() == 1\n")
        assert check_quantifier(graph) == []
