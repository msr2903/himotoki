"""Tests for database models and connection."""

import os
import tempfile
from pathlib import Path

import pytest

from himotoki.db.models import (
    Entry,
    KanjiText,
    KanaText,
    Sense,
    Gloss,
    SenseProp,
    RestrictedReading,
    Conjugation,
    ConjProp,
    ConjSourceReading,
    Base,
)
from himotoki.db.connection import (
    init_database,
    get_session,
    session_scope,
    close_connection,
    get_cache,
    set_cache,
    clear_cache,
    ensure_cache,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        os.environ["HIMOTOKI_DB_PATH"] = str(db_path)
        init_database(str(db_path), drop_existing=True)
        yield db_path
        close_connection()
        if "HIMOTOKI_DB_PATH" in os.environ:
            del os.environ["HIMOTOKI_DB_PATH"]


class TestDatabaseModels:
    """Test database model creation and relationships."""

    def test_create_entry(self, temp_db):
        """Test creating a basic entry."""
        with session_scope() as session:
            entry = Entry(
                seq=1000000,
                content="<test/>",
                root_p=True,
                n_kanji=1,
                n_kana=1,
            )
            session.add(entry)
            session.flush()

            # Query it back
            queried = session.query(Entry).filter_by(seq=1000000).first()
            assert queried is not None
            assert queried.seq == 1000000
            assert queried.root_p is True
            assert queried.n_kanji == 1

    def test_entry_with_kanji_kana(self, temp_db):
        """Test creating an entry with kanji and kana readings."""
        with session_scope() as session:
            entry = Entry(
                seq=1000001,
                content="<test/>",
                root_p=True,
                n_kanji=1,
                n_kana=1,
            )
            session.add(entry)
            session.flush()

            kanji = KanjiText(
                seq=1000001,
                text="学校",
                ord=0,
                common=10,
                best_kana="がっこう",
            )
            session.add(kanji)

            kana = KanaText(
                seq=1000001,
                text="がっこう",
                ord=0,
                common=10,
                best_kanji="学校",
            )
            session.add(kana)
            session.flush()

            # Query and verify relationships
            queried = session.query(Entry).filter_by(seq=1000001).first()
            assert len(queried.kanji_texts) == 1
            assert len(queried.kana_texts) == 1
            assert queried.kanji_texts[0].text == "学校"
            assert queried.kana_texts[0].text == "がっこう"

    def test_sense_and_gloss(self, temp_db):
        """Test creating senses and glosses."""
        with session_scope() as session:
            entry = Entry(seq=1000002, content="", root_p=True)
            session.add(entry)
            session.flush()

            sense = Sense(seq=1000002, ord=0)
            session.add(sense)
            session.flush()

            gloss = Gloss(sense_id=sense.id, text="school", ord=0)
            session.add(gloss)

            prop = SenseProp(
                sense_id=sense.id,
                seq=1000002,
                tag="pos",
                text="n",
                ord=0,
            )
            session.add(prop)
            session.flush()

            # Query and verify
            queried_sense = session.query(Sense).filter_by(seq=1000002).first()
            assert len(queried_sense.glosses) == 1
            assert queried_sense.glosses[0].text == "school"
            assert len(queried_sense.props) == 1
            assert queried_sense.props[0].tag == "pos"

    def test_conjugation_relationships(self, temp_db):
        """Test conjugation relationships between entries."""
        with session_scope() as session:
            # Root entry (e.g., 食べる)
            root = Entry(seq=1000010, content="", root_p=True)
            session.add(root)
            
            # Conjugated entry (e.g., 食べた)
            conj_entry = Entry(seq=1000011, content="", root_p=False)
            session.add(conj_entry)
            session.flush()

            # Conjugation link
            conj = Conjugation(seq=1000011, from_seq=1000010, via=None)
            session.add(conj)
            session.flush()

            # Conjugation properties
            prop = ConjProp(
                conj_id=conj.id,
                conj_type=2,  # Plain form
                pos="v1",
                neg=False,
                fml=False,
            )
            session.add(prop)

            # Source reading
            src = ConjSourceReading(
                conj_id=conj.id,
                text="食べた",
                source_text="食べる",
            )
            session.add(src)
            session.flush()

            # Query and verify
            queried_conj = session.query(Conjugation).filter_by(seq=1000011).first()
            assert queried_conj.from_seq == 1000010
            assert len(queried_conj.props) == 1
            assert queried_conj.props[0].conj_type == 2
            assert len(queried_conj.source_readings) == 1
            assert queried_conj.source_readings[0].source_text == "食べる"

    def test_restricted_reading(self, temp_db):
        """Test restricted reading relationships."""
        with session_scope() as session:
            entry = Entry(seq=1000020, content="", root_p=True)
            session.add(entry)
            session.flush()

            restricted = RestrictedReading(
                seq=1000020,
                reading="あす",
                text="明日",
            )
            session.add(restricted)
            session.flush()

            queried = session.query(RestrictedReading).filter_by(seq=1000020).first()
            assert queried.reading == "あす"
            assert queried.text == "明日"


class TestCacheSystem:
    """Test the cache system."""

    def test_set_and_get_cache(self, temp_db):
        """Test basic cache operations."""
        clear_cache()
        
        set_cache("test_key", {"data": 123})
        result = get_cache("test_key")
        assert result == {"data": 123}

    def test_clear_cache(self, temp_db):
        """Test cache clearing."""
        clear_cache()
        
        set_cache("key1", "value1")
        set_cache("key2", "value2")
        
        clear_cache("key1")
        assert get_cache("key1") is None
        assert get_cache("key2") == "value2"
        
        clear_cache()
        assert get_cache("key2") is None

    def test_ensure_cache(self, temp_db):
        """Test ensure_cache initialization."""
        clear_cache()
        
        call_count = [0]
        
        def initializer():
            call_count[0] += 1
            return {"initialized": True}
        
        # First call should initialize
        result1 = ensure_cache("ensure_test", initializer)
        assert result1 == {"initialized": True}
        assert call_count[0] == 1
        
        # Second call should return cached value
        result2 = ensure_cache("ensure_test", initializer)
        assert result2 == {"initialized": True}
        assert call_count[0] == 1  # Initializer not called again


class TestQueryPatterns:
    """Test common query patterns used in ichiran."""

    def test_find_word_by_text(self, temp_db):
        """Test finding words by text (like find_word in ichiran)."""
        with session_scope() as session:
            # Create test data
            entry = Entry(seq=1000030, content="", root_p=True, n_kanji=1, n_kana=1)
            session.add(entry)
            session.flush()

            kanji = KanjiText(seq=1000030, text="日本語", ord=0, common=5)
            kana = KanaText(seq=1000030, text="にほんご", ord=0, common=5)
            session.add_all([kanji, kana])
            session.flush()

            # Query by kanji text
            result = session.query(KanjiText).filter_by(text="日本語").all()
            assert len(result) == 1
            assert result[0].seq == 1000030

            # Query by kana text
            result = session.query(KanaText).filter_by(text="にほんご").all()
            assert len(result) == 1
            assert result[0].seq == 1000030

    def test_find_conjugations(self, temp_db):
        """Test finding conjugations for an entry."""
        with session_scope() as session:
            # Create root and conjugated entries
            root = Entry(seq=1000040, content="", root_p=True)
            conj1 = Entry(seq=1000041, content="", root_p=False)
            conj2 = Entry(seq=1000042, content="", root_p=False)
            session.add_all([root, conj1, conj2])
            session.flush()

            c1 = Conjugation(seq=1000041, from_seq=1000040)
            c2 = Conjugation(seq=1000042, from_seq=1000040)
            session.add_all([c1, c2])
            session.flush()

            # Query conjugations from root
            conjs = session.query(Conjugation).filter_by(from_seq=1000040).all()
            assert len(conjs) == 2
            assert set(c.seq for c in conjs) == {1000041, 1000042}

    def test_find_senses_with_pos(self, temp_db):
        """Test finding senses by part-of-speech."""
        with session_scope() as session:
            entry = Entry(seq=1000050, content="", root_p=True)
            session.add(entry)
            session.flush()

            sense = Sense(seq=1000050, ord=0)
            session.add(sense)
            session.flush()

            # Add multiple POS tags
            props = [
                SenseProp(sense_id=sense.id, seq=1000050, tag="pos", text="n", ord=0),
                SenseProp(sense_id=sense.id, seq=1000050, tag="pos", text="adj-na", ord=1),
            ]
            session.add_all(props)
            session.flush()

            # Query by POS
            results = (
                session.query(SenseProp)
                .filter_by(seq=1000050, tag="pos")
                .all()
            )
            assert len(results) == 2
            pos_texts = [r.text for r in results]
            assert "n" in pos_texts
            assert "adj-na" in pos_texts