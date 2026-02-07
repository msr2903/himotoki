"""
Tests for the conjugation breakdown tree feature.

Tests the _get_conjugation_display, _get_compound_display, format_conjugation_info,
_build_conj_chain, _collect_via_steps, _get_conj_suffix, and _extract_suffix functions
in himotoki/output.py.
"""

import pytest

from himotoki.output import (
    dict_segment,
    _get_conjugation_display,
    _extract_suffix,
    ConjStep,
    WordType,
)
from himotoki.suffixes import init_suffixes


@pytest.fixture(scope="module")
def session_with_suffixes(db_session):
    """Database session with suffix system initialized (needed for compound detection)."""
    init_suffixes(db_session)
    return db_session


def _get_tree(session, text):
    """Helper: segment text and return (word_infos, tree_lines) for the first non-gap word."""
    results = dict_segment(session, text, limit=1)
    assert results, f"No segmentation results for: {text}"
    wis, score = results[0]
    for wi in wis:
        if wi.type == WordType.GAP:
            continue
        tree = _get_conjugation_display(session, wi)
        return wi, tree
    return None, []


def _get_all_trees(session, text):
    """Helper: segment text and return list of (wi, tree_lines) for all non-gap words."""
    results = dict_segment(session, text, limit=1)
    assert results, f"No segmentation results for: {text}"
    wis, score = results[0]
    result = []
    for wi in wis:
        if wi.type == WordType.GAP:
            continue
        tree = _get_conjugation_display(session, wi)
        result.append((wi, tree))
    return result


# =============================================================================
# Unit tests for _extract_suffix
# =============================================================================


class TestExtractSuffix:
    """Unit tests for suffix extraction logic."""

    def test_simple_past(self):
        assert _extract_suffix("たべた", "たべる") == "た"

    def test_te_form(self):
        assert _extract_suffix("はしって", "はしる") == "って"

    def test_polite_past(self):
        assert _extract_suffix("いきました", "いく") == "きました"

    def test_passive(self):
        assert _extract_suffix("よまれる", "よむ") == "まれる"

    def test_potential(self):
        assert _extract_suffix("よめる", "よむ") == "める"

    def test_negative(self):
        assert _extract_suffix("たべない", "たべる") == "ない"

    def test_negative_past(self):
        assert _extract_suffix("のまなかった", "のむ") == "まなかった"

    def test_causative(self):
        assert _extract_suffix("かかせる", "かく") == "かせる"

    def test_volitional(self):
        assert _extract_suffix("いこう", "いく") == "こう"

    def test_conditional(self):
        assert _extract_suffix("たべたら", "たべる") == "たら"

    def test_provisional(self):
        assert _extract_suffix("いけば", "いく") == "けば"

    def test_no_common_prefix(self):
        # When texts diverge from the start, return full conjugated text
        assert _extract_suffix("した", "する") == "した"

    def test_identical_texts(self):
        # When identical, return full text as fallback
        assert _extract_suffix("いる", "いる") == "いる"

    def test_single_char(self):
        assert _extract_suffix("た", "る") == "た"

    def test_empty_string(self):
        assert _extract_suffix("", "") == ""


# =============================================================================
# Integration tests: simple conjugation patterns
# =============================================================================


class TestSimpleConjugation:
    """Test basic single-step conjugation display."""

    def test_past_tense(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べた")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree), f"Root not found in: {tree}"
        assert any("Past" in line for line in tree), f"Past not found in: {tree}"

    def test_negative(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べない")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree)
        assert any("not" in line.lower() for line in tree)

    def test_polite_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "行きました")
        assert len(tree) >= 3
        assert any("行く" in line for line in tree)
        assert any("Polite" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_te_form(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "走って")
        assert len(tree) >= 2
        assert any("走る" in line for line in tree)
        assert any("Conjunctive" in line or "~te" in line for line in tree)

    def test_volitional(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "行こう")
        assert len(tree) >= 2
        assert any("行く" in line for line in tree)
        assert any("Volitional" in line for line in tree)

    def test_imperative(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べろ")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree)
        assert any("Imperative" in line for line in tree)

    def test_conditional(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べたら")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree)
        assert any("Conditional" in line for line in tree)

    def test_provisional(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "行けば")
        assert len(tree) >= 2
        assert any("行く" in line for line in tree)
        assert any("Provisional" in line for line in tree)

    def test_alternative(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べたり")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree)
        assert any("Alternative" in line for line in tree)

    def test_polite_nonpast(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べます")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree)
        assert any("Polite" in line for line in tree)

    def test_polite_negative(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べません")
        assert len(tree) >= 3
        assert any("食べる" in line for line in tree)
        assert any("Polite" in line for line in tree)
        assert any("not" in line.lower() for line in tree)

    def test_polite_volitional(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べましょう")
        assert len(tree) >= 3
        assert any("食べる" in line for line in tree)
        assert any("Volitional" in line for line in tree)
        assert any("Polite" in line for line in tree)


# =============================================================================
# Integration tests: adjective conjugation
# =============================================================================


class TestAdjectiveConjugation:
    """Test adjective conjugation display."""

    def test_adj_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "美しかった")
        assert len(tree) >= 2
        assert any("美しい" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_adj_negative(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "楽しくない")
        assert len(tree) >= 2
        assert any("楽しい" in line for line in tree)
        assert any("not" in line.lower() for line in tree)

    def test_adj_negative_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "美しくなかった")
        assert len(tree) >= 2
        assert any("美しい" in line for line in tree)
        assert any("not" in line.lower() for line in tree)
        assert any("Past" in line for line in tree)

    def test_adj_adverbial(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "美しく")
        assert len(tree) >= 2
        assert any("美しい" in line for line in tree)
        assert any("Adverbial" in line for line in tree)

    def test_adj_te_form(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "高くて")
        assert len(tree) >= 2
        assert any("高い" in line for line in tree)
        assert any("Conjunctive" in line or "~te" in line for line in tree)


# =============================================================================
# Integration tests: via chains (multi-step conjugation)
# =============================================================================


class TestViaChains:
    """Test multi-step conjugation chains using the via field."""

    def test_passive_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "読まれた")
        assert len(tree) >= 3
        assert any("読む" in line for line in tree)
        assert any("Passive" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_causative_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "書かせた")
        assert len(tree) >= 3
        assert any("書く" in line for line in tree)
        assert any("Causative" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_causative_passive(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "書かせられた")
        assert len(tree) >= 3
        assert any("書く" in line for line in tree)
        assert any("Causative-Passive" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_potential_negative_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べられなかった")
        assert len(tree) >= 3
        assert any("食べる" in line for line in tree)
        assert any("not" in line.lower() for line in tree)
        assert any("Past" in line for line in tree)

    def test_potential_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "読めた")
        assert len(tree) >= 3
        assert any("読む" in line for line in tree)
        assert any("Potential" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_passive_polite_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "読まれました")
        assert len(tree) >= 4
        assert any("読む" in line for line in tree)
        assert any("Passive" in line for line in tree)
        assert any("Polite" in line for line in tree)
        assert any("Past" in line for line in tree)


# =============================================================================
# Integration tests: compound words (suffix compounds)
# =============================================================================


class TestCompoundDisplay:
    """Test conjugation display for suffix compound words."""

    def test_te_iru(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べている")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree)
        assert any("Conjunctive" in line or "~te" in line for line in tree)

    def test_te_iru_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "走っていた")
        assert len(tree) >= 3
        assert any("走る" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_te_shimau(self, session_with_suffixes):
        """Test 忘れてしまった shows single root (no duplicate from archaic 忘る)."""
        wi, tree = _get_tree(session_with_suffixes, "忘れてしまった")
        assert len(tree) >= 3
        # Should have exactly one root line
        root_lines = [l for l in tree if "←" in l]
        assert len(root_lines) == 1, f"Expected 1 root line, got {len(root_lines)}: {root_lines}"
        assert any("忘れる" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_te_kureru(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "教えてくれた")
        assert len(tree) >= 3
        assert any("教える" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_te_morau(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "読んでもらった")
        assert len(tree) >= 3
        assert any("読む" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_desiderative(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べたい")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree)
        assert any("たい" in line for line in tree)

    def test_desiderative_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べたかった")
        assert len(tree) >= 3
        assert any("食べる" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_adj_sou(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "美味しそう")
        assert len(tree) >= 2
        assert any("美味しい" in line for line in tree)
        assert any("そう" in line for line in tree)

    def test_causative_passive_te_iru(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "書かせられている")
        assert len(tree) >= 3
        assert any("書く" in line for line in tree)
        assert any("Causative-Passive" in line for line in tree)
        assert any("Conjunctive" in line or "~te" in line for line in tree)


# =============================================================================
# Integration tests: multi-alternative compound words (Bug #1 regression)
# =============================================================================


class TestMultiAlternativeCompound:
    """Test that multi-alternative compound words show conjugation trees.
    
    This was Bug #1: words like 食べられていた have multiple alternative
    analyses (potential vs passive) and are compounds. The merged WordInfo
    had alternative=True, is_compound=False, causing empty tree output.
    """

    def test_taberareteita(self, session_with_suffixes):
        """食べられていた must show a conjugation tree (was empty before fix)."""
        wi, tree = _get_tree(session_with_suffixes, "食べられていた")
        assert len(tree) >= 3, f"Expected 3+ tree lines, got {len(tree)}: {tree}"
        assert any("食べる" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_compared_to_single_alternative(self, session_with_suffixes):
        """読まれていた (single alternative) should also work."""
        wi, tree = _get_tree(session_with_suffixes, "読まれていた")
        assert len(tree) >= 3
        assert any("読む" in line for line in tree)


# =============================================================================
# Integration tests: suffix extraction quality (Bug #3 regression)
# =============================================================================


class TestSuffixExtraction:
    """Test that suffix extraction avoids variant kanji issues.
    
    Bug #3: has_kanji preference picked variant kanji (喰べ for 食べ,
    旨味し for 美味し) that broke _extract_suffix.
    """

    def test_no_variant_kanji_in_desiderative(self, session_with_suffixes):
        """食べたい should NOT show 喰べ in the tree."""
        wi, tree = _get_tree(session_with_suffixes, "食べたい")
        for line in tree:
            assert "喰" not in line, f"Variant kanji 喰 found in: {line}"

    def test_no_variant_kanji_in_sou(self, session_with_suffixes):
        """美味しそう should NOT show 旨味し in the tree."""
        wi, tree = _get_tree(session_with_suffixes, "美味しそう")
        for line in tree:
            assert "旨味" not in line, f"Variant kanji 旨味 found in: {line}"

    def test_no_variant_kanji_in_tai_neg(self, session_with_suffixes):
        """食べたくない should NOT show 喰 in the tree."""
        wi, tree = _get_tree(session_with_suffixes, "食べたくない")
        for line in tree:
            assert "喰" not in line, f"Variant kanji 喰 found in: {line}"

    def test_no_variant_kanji_in_tai_neg_past(self, session_with_suffixes):
        """食べたくなかった should NOT show 喰 in the tree."""
        wi, tree = _get_tree(session_with_suffixes, "食べたくなかった")
        for line in tree:
            assert "喰" not in line, f"Variant kanji 喰 found in: {line}"


# =============================================================================
# Integration tests: deep chains
# =============================================================================


class TestDeepChains:
    """Test very deep conjugation chains with many steps."""

    def test_te_shimau_tai_past(self, session_with_suffixes):
        """飲んでしまいたかった: te + shimau + tai + past."""
        wi, tree = _get_tree(session_with_suffixes, "飲んでしまいたかった")
        assert len(tree) >= 4
        assert any("飲む" in line for line in tree)
        assert any("Conjunctive" in line or "~te" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_te_shimau_tai_neg_past(self, session_with_suffixes):
        """飲んでしまいたくなかった: te + shimau + tai + neg + past."""
        wi, tree = _get_tree(session_with_suffixes, "飲んでしまいたくなかった")
        assert len(tree) >= 4
        assert any("飲む" in line for line in tree)
        assert any("not" in line.lower() for line in tree)

    def test_causative_passive_te_iru_past(self, session_with_suffixes):
        """書かせられていた: causative-passive + te + iru + past."""
        wi, tree = _get_tree(session_with_suffixes, "書かせられていた")
        assert len(tree) >= 4
        assert any("書く" in line for line in tree)
        assert any("Causative-Passive" in line for line in tree)
        assert any("Past" in line for line in tree)


# =============================================================================
# Integration tests: irregular verbs
# =============================================================================


class TestIrregularVerbs:
    """Test irregular verb conjugation display."""

    def test_kuru_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "来た")
        assert len(tree) >= 2
        assert any("来る" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_suru_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "した")
        assert len(tree) >= 2
        assert any("Past" in line for line in tree)

    def test_copula_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "だった")
        assert len(tree) >= 2
        assert any("Past" in line for line in tree)

    def test_copula_polite_past(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "でした")
        assert len(tree) >= 2
        assert any("Polite" in line for line in tree)
        assert any("Past" in line for line in tree)


# =============================================================================
# Integration tests: godan verb types
# =============================================================================


class TestGodanVerbs:
    """Test various godan verb ending types."""

    def test_bu_verb(self, session_with_suffixes):
        """遊んだ (bu-ending → nda past)."""
        wi, tree = _get_tree(session_with_suffixes, "遊んだ")
        assert len(tree) >= 2
        assert any("遊ぶ" in line for line in tree)

    def test_gu_verb(self, session_with_suffixes):
        """泳いだ (gu-ending → ida past)."""
        wi, tree = _get_tree(session_with_suffixes, "泳いだ")
        assert len(tree) >= 2
        assert any("泳ぐ" in line for line in tree)

    def test_su_verb(self, session_with_suffixes):
        """話しました (su-ending polite past)."""
        wi, tree = _get_tree(session_with_suffixes, "話しました")
        assert len(tree) >= 2
        assert any("話す" in line for line in tree)

    def test_tsu_verb(self, session_with_suffixes):
        """待って (tsu-ending → tte te-form)."""
        wi, tree = _get_tree(session_with_suffixes, "待って")
        assert len(tree) >= 2
        assert any("待つ" in line for line in tree)


# =============================================================================
# Integration tests: unconjugated (no tree expected)
# =============================================================================


class TestNoConjugation:
    """Test that dictionary forms and non-conjugable words show no tree."""

    def test_dictionary_form_verb(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べる")
        assert len(tree) == 0, f"Unexpected tree for dictionary form: {tree}"

    def test_noun(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "学校")
        assert len(tree) == 0, f"Unexpected tree for noun: {tree}"

    def test_particle(self, session_with_suffixes):
        trees = _get_all_trees(session_with_suffixes, "が")
        for wi, tree in trees:
            assert len(tree) == 0, f"Unexpected tree for particle: {tree}"


# =============================================================================
# Integration tests: tree structure integrity
# =============================================================================


class TestTreeStructure:
    """Test that the tree formatting follows correct structure."""

    def test_root_line_has_arrow(self, session_with_suffixes):
        """Every tree must start with a ← root line."""
        wi, tree = _get_tree(session_with_suffixes, "食べた")
        assert tree[0].strip().startswith("←"), f"Expected root arrow, got: {tree[0]}"

    def test_steps_have_box_drawing(self, session_with_suffixes):
        """Non-root lines must use └─ box-drawing characters."""
        wi, tree = _get_tree(session_with_suffixes, "食べた")
        for line in tree[1:]:
            assert "└─" in line, f"Expected └─ in: {line}"

    def test_steps_have_gloss(self, session_with_suffixes):
        """Each conjugation step line should have a colon-separated gloss."""
        wi, tree = _get_tree(session_with_suffixes, "食べた")
        for line in tree[1:]:
            if "└─" in line and "【" not in line and "Polite" not in line:
                # Skip suffix component lines and Polite-only lines
                assert ":" in line, f"Expected gloss (colon) in: {line}"

    def test_indentation_increases(self, session_with_suffixes):
        """Each subsequent step should have deeper indentation."""
        wi, tree = _get_tree(session_with_suffixes, "読まれた")
        if len(tree) >= 3:
            # Get indentation levels
            indents = []
            for line in tree[1:]:  # Skip root line
                stripped = line.lstrip()
                indent = len(line) - len(stripped)
                indents.append(indent)
            # Each step should be at least as indented as the previous
            for i in range(1, len(indents)):
                assert indents[i] >= indents[i-1], \
                    f"Indentation decreased at step {i}: {indents} in tree: {tree}"

    def test_compound_tree_no_duplicate_roots(self, session_with_suffixes):
        """Compound trees should have at most one ← root line."""
        test_cases = ["食べている", "走っていた", "忘れてしまった", "食べたい"]
        for text in test_cases:
            wi, tree = _get_tree(session_with_suffixes, text)
            root_lines = [l for l in tree if "←" in l]
            assert len(root_lines) <= 1, \
                f"Multiple root lines for {text}: {root_lines}"


# =============================================================================
# Integration tests: ConjStep dataclass
# =============================================================================


class TestConjStep:
    """Test ConjStep dataclass construction."""

    def test_basic_creation(self):
        step = ConjStep(conj_type="Past (~ta)", suffix="た", gloss="did/was")
        assert step.conj_type == "Past (~ta)"
        assert step.suffix == "た"
        assert step.gloss == "did/was"
        assert step.neg is False
        assert step.fml is False

    def test_negative_step(self):
        step = ConjStep(conj_type="Non-past", suffix="ない", gloss="not does/is", neg=True)
        assert step.neg is True
        assert step.fml is False

    def test_formal_step(self):
        step = ConjStep(conj_type="Past (~ta)", suffix="ました", gloss="did/was", fml=True)
        assert step.fml is True
        assert step.neg is False

    def test_formal_negative_step(self):
        step = ConjStep(
            conj_type="Non-past", suffix="ません",
            gloss="not does/is", neg=True, fml=True
        )
        assert step.neg is True
        assert step.fml is True


# =============================================================================
# Integration tests: keigo and contractions
# =============================================================================


class TestSpecialForms:
    """Test honorific and contracted forms."""

    def test_irasshaimashita(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "いらっしゃいました")
        assert len(tree) >= 3
        assert any("Polite" in line for line in tree)
        assert any("Past" in line for line in tree)

    def test_chau_contraction(self, session_with_suffixes):
        wi, tree = _get_tree(session_with_suffixes, "食べちゃった")
        assert len(tree) >= 2
        assert any("食べる" in line for line in tree)
        assert any("Past" in line for line in tree)
