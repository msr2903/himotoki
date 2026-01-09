"""
SQLAlchemy ORM models for the himotoki dictionary database.
These models match the ichiran PostgreSQL schema, adapted for SQLite.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Text,
    ForeignKey,
    Index,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Entry(Base):
    """
    Main dictionary entry table.
    Each entry corresponds to a JMDict entry with a unique seq (sequence number).
    """
    __tablename__ = "entry"

    seq = Column(Integer, primary_key=True)
    content = Column(Text, nullable=False, default="")  # Original XML content
    root_p = Column(Boolean, nullable=False, default=False)  # True if this is a root entry (not conjugation)
    n_kanji = Column(Integer, nullable=False, default=0)  # Number of kanji readings
    n_kana = Column(Integer, nullable=False, default=0)  # Number of kana readings
    primary_nokanji = Column(Boolean, nullable=False, default=False)  # True if primary reading has no kanji

    # Relationships
    kanji_texts = relationship("KanjiText", back_populates="entry", cascade="all, delete-orphan")
    kana_texts = relationship("KanaText", back_populates="entry", cascade="all, delete-orphan")
    senses = relationship("Sense", back_populates="entry", cascade="all, delete-orphan")
    restricted_readings = relationship("RestrictedReading", back_populates="entry", cascade="all, delete-orphan")
    sense_props = relationship("SenseProp", back_populates="entry", cascade="all, delete-orphan")
    
    # Conjugation relationships
    conjugations_to = relationship(
        "Conjugation", 
        foreign_keys="Conjugation.seq",
        back_populates="entry",
        cascade="all, delete-orphan"
    )
    conjugations_from = relationship(
        "Conjugation",
        foreign_keys="Conjugation.from_seq",
        back_populates="source_entry"
    )

    def __repr__(self):
        return f"<Entry(seq={self.seq}, n_kanji={self.n_kanji}, n_kana={self.n_kana})>"


class KanjiText(Base):
    """
    Kanji reading for an entry.
    Stores the text, ordinal position, and commonness information.
    """
    __tablename__ = "kanji_text"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seq = Column(Integer, ForeignKey("entry.seq", ondelete="CASCADE"), nullable=False)
    text = Column(String(255), nullable=False)
    ord = Column(Integer, nullable=False)  # Order within the entry
    common = Column(Integer, nullable=True)  # Commonness score (lower = more common, NULL = not common)
    common_tags = Column(String(255), nullable=False, default="")  # Priority tags like [news1]
    conjugate_p = Column(Boolean, nullable=False, default=True)  # Whether to generate conjugations
    nokanji = Column(Boolean, nullable=False, default=False)  # True if reading has no kanji
    best_kana = Column(String(255), nullable=True)  # Best matching kana reading

    # Relationships
    entry = relationship("Entry", back_populates="kanji_texts")

    __table_args__ = (
        Index("ix_kanji_text_seq", "seq"),
        Index("ix_kanji_text_ord", "ord"),
        Index("ix_kanji_text_text", "text"),
        Index("ix_kanji_text_common", "common"),
        # Composite indexes for common query patterns
        Index("ix_kanji_text_text_seq", "text", "seq"),  # find_word lookups
        Index("ix_kanji_text_seq_ord", "seq", "ord"),  # ordered retrieval by entry
    )

    def __repr__(self):
        return f"<KanjiText(id={self.id}, seq={self.seq}, text='{self.text}')>"


class KanaText(Base):
    """
    Kana reading for an entry.
    Stores the text, ordinal position, and commonness information.
    """
    __tablename__ = "kana_text"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seq = Column(Integer, ForeignKey("entry.seq", ondelete="CASCADE"), nullable=False)
    text = Column(String(255), nullable=False)
    ord = Column(Integer, nullable=False)  # Order within the entry
    common = Column(Integer, nullable=True)  # Commonness score (lower = more common, NULL = not common)
    common_tags = Column(String(255), nullable=False, default="")  # Priority tags like [news1]
    conjugate_p = Column(Boolean, nullable=False, default=True)  # Whether to generate conjugations
    nokanji = Column(Boolean, nullable=False, default=False)  # True if this reading doesn't use kanji
    best_kanji = Column(String(255), nullable=True)  # Best matching kanji reading

    # Relationships
    entry = relationship("Entry", back_populates="kana_texts")

    __table_args__ = (
        Index("ix_kana_text_seq", "seq"),
        Index("ix_kana_text_ord", "ord"),
        Index("ix_kana_text_text", "text"),
        Index("ix_kana_text_common", "common"),
        # Composite indexes for common query patterns
        Index("ix_kana_text_text_seq", "text", "seq"),  # find_word lookups
        Index("ix_kana_text_seq_ord", "seq", "ord"),  # ordered retrieval by entry
    )

    def __repr__(self):
        return f"<KanaText(id={self.id}, seq={self.seq}, text='{self.text}')"


class Sense(Base):
    """
    A sense (meaning group) within an entry.
    Each entry can have multiple senses.
    """
    __tablename__ = "sense"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seq = Column(Integer, ForeignKey("entry.seq", ondelete="CASCADE"), nullable=False)
    ord = Column(Integer, nullable=False)  # Order within the entry

    # Relationships
    entry = relationship("Entry", back_populates="senses")
    glosses = relationship("Gloss", back_populates="sense", cascade="all, delete-orphan")
    props = relationship("SenseProp", back_populates="sense", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_sense_seq", "seq"),
    )

    def __repr__(self):
        return f"<Sense(id={self.id}, seq={self.seq}, ord={self.ord})>"


class Gloss(Base):
    """
    English gloss (translation) for a sense.
    Each sense can have multiple glosses.
    """
    __tablename__ = "gloss"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sense_id = Column(Integer, ForeignKey("sense.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    ord = Column(Integer, nullable=False)  # Order within the sense

    # Relationships
    sense = relationship("Sense", back_populates="glosses")

    __table_args__ = (
        Index("ix_gloss_sense_id", "sense_id"),
    )

    def __repr__(self):
        return f"<Gloss(id={self.id}, sense_id={self.sense_id}, text='{self.text[:30]}...')>"


class SenseProp(Base):
    """
    Sense property (part-of-speech, dialect, field, etc.).
    Tags include: pos, misc, dial, field, s_inf, stagk, stagr
    """
    __tablename__ = "sense_prop"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sense_id = Column(Integer, ForeignKey("sense.id", ondelete="CASCADE"), nullable=False)
    seq = Column(Integer, ForeignKey("entry.seq", ondelete="CASCADE"), nullable=False)
    tag = Column(String(50), nullable=False)  # Property type (pos, misc, dial, field, s_inf, stagk, stagr)
    text = Column(String(255), nullable=False)  # Property value
    ord = Column(Integer, nullable=False)  # Order within the sense

    # Relationships
    sense = relationship("Sense", back_populates="props")
    entry = relationship("Entry", back_populates="sense_props")

    __table_args__ = (
        Index("ix_sense_prop_sense_id_tag", "sense_id", "tag"),
        Index("ix_sense_prop_tag_text", "tag", "text"),
        Index("ix_sense_prop_seq_tag_text", "seq", "tag", "text"),
    )

    def __repr__(self):
        return f"<SenseProp(id={self.id}, tag='{self.tag}', text='{self.text}')>"


class RestrictedReading(Base):
    """
    Maps restricted kana readings to their applicable kanji forms.
    Used when a kana reading only applies to certain kanji forms.
    """
    __tablename__ = "restricted_reading"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seq = Column(Integer, ForeignKey("entry.seq", ondelete="CASCADE"), nullable=False)
    reading = Column(String(255), nullable=False)  # The kana reading
    text = Column(String(255), nullable=False)  # The kanji text it applies to

    # Relationships
    entry = relationship("Entry", back_populates="restricted_readings")

    __table_args__ = (
        Index("ix_restricted_reading_seq_reading", "seq", "reading"),
    )

    def __repr__(self):
        return f"<RestrictedReading(id={self.id}, reading='{self.reading}', text='{self.text}')>"


class Conjugation(Base):
    """
    Links conjugated forms to their root entries.
    A conjugated entry (seq) is derived from a root entry (from_seq).
    Via is used for secondary conjugations (e.g., causative-passive).
    """
    __tablename__ = "conjugation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seq = Column(Integer, ForeignKey("entry.seq", ondelete="CASCADE"), nullable=False)
    from_seq = Column("from", Integer, ForeignKey("entry.seq", ondelete="CASCADE"), nullable=False)
    via = Column(Integer, nullable=True)  # Intermediate form for secondary conjugations

    # Relationships
    entry = relationship("Entry", foreign_keys=[seq], back_populates="conjugations_to")
    source_entry = relationship("Entry", foreign_keys=[from_seq], back_populates="conjugations_from")
    props = relationship("ConjProp", back_populates="conjugation", cascade="all, delete-orphan")
    source_readings = relationship("ConjSourceReading", back_populates="conjugation", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_conjugation_seq", "seq"),
        Index("ix_conjugation_from", "from"),
        # Composite index for conjugation chain lookups
        Index("ix_conjugation_from_via", "from", "via"),
    )

    def __repr__(self):
        return f"<Conjugation(id={self.id}, seq={self.seq}, from={self.from_seq}, via={self.via})>"


class ConjProp(Base):
    """
    Conjugation properties.
    Stores the conjugation type, part-of-speech, and form details.
    """
    __tablename__ = "conj_prop"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conj_id = Column(Integer, ForeignKey("conjugation.id", ondelete="CASCADE"), nullable=False)
    conj_type = Column(Integer, nullable=False)  # Conjugation type code (1=negative, 2=plain, 3=te-form, etc.)
    pos = Column(String(50), nullable=False)  # Part-of-speech
    neg = Column(Boolean, nullable=True)  # True=negative, False=affirmative, None=not applicable
    fml = Column(Boolean, nullable=True)  # True=formal, False=plain, None=not applicable

    # Relationships
    conjugation = relationship("Conjugation", back_populates="props")

    __table_args__ = (
        Index("ix_conj_prop_conj_id", "conj_id"),
    )

    def __repr__(self):
        return f"<ConjProp(id={self.id}, conj_type={self.conj_type}, pos='{self.pos}', neg={self.neg}, fml={self.fml})>"


class ConjSourceReading(Base):
    """
    Maps conjugated text to its source (unconjugated) text.
    Used to track how each conjugated form was derived.
    """
    __tablename__ = "conj_source_reading"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conj_id = Column(Integer, ForeignKey("conjugation.id", ondelete="CASCADE"), nullable=False)
    text = Column(String(255), nullable=False)  # The conjugated text
    source_text = Column(String(255), nullable=False)  # The source (unconjugated) text

    # Relationships
    conjugation = relationship("Conjugation", back_populates="source_readings")

    __table_args__ = (
        Index("ix_conj_source_reading_conj_id_text", "conj_id", "text"),
    )

    def __repr__(self):
        return f"<ConjSourceReading(id={self.id}, text='{self.text}', source_text='{self.source_text}')>"


# Conjugation type constants (from ichiran)
CONJ_NEGATIVE = 1
CONJ_PLAIN = 2
CONJ_TE_FORM = 3
CONJ_CONDITIONAL = 4
CONJ_CAUSATIVE = 5
CONJ_PASSIVE = 6
CONJ_CAUSATIVE_PASSIVE = 7
CONJ_POTENTIAL = 8
CONJ_VOLITIONAL = 9
CONJ_CONTINUATIVE = 10  # Ren'youkei
CONJ_IMPERATIVE = 11
CONJ_ADJECTIVE_STEM = 12
CONJ_ADVERBIAL = 13
CONJ_ADJECTIVE_LITERARY = 14
CONJ_NEGATIVE_STEM = 15
CONJ_CAUSATIVE_SU = 16  # Alternative causative with す


def create_all_tables(engine):
    """Create all tables in the database."""
    Base.metadata.create_all(engine)


def drop_all_tables(engine):
    """Drop all tables from the database."""
    Base.metadata.drop_all(engine)