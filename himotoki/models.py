"""
Pydantic models for himotoki API responses.

These models are designed for use with FastAPI and provide:
- Type-safe response schemas
- Automatic JSON serialization
- OpenAPI documentation generation

Usage:
    from himotoki.models import WordResult, AnalysisResult, VocabularyResult
    
    # In FastAPI:
    @app.get("/analyze", response_model=AnalysisResult)
    async def analyze_endpoint(text: str):
        results = await himotoki.analyze_async(text)
        return AnalysisResult.from_analysis(results)
    
    @app.post("/analyze_simple", response_model=VocabularyResult)
    async def vocabulary_endpoint(text: str):
        results = await himotoki.analyze_async(text)
        return VocabularyResult.from_analysis(results)
"""

from typing import List, Optional, Any, Set
from pydantic import BaseModel, Field


# =============================================================================
# Constants for Filtering
# =============================================================================

# POS tags that represent content words (not grammatical particles)
# Used by VocabularyResult to filter out particles
CONTENT_WORD_POS: Set[str] = {
    'n', 'v1', 'v5', 'v5k', 'v5s', 'v5t', 'v5n', 'v5m', 'v5r', 'v5u', 'v5g', 'v5b',
    'v5k-s', 'v5aru', 'vk', 'vs', 'vs-i', 'vs-s', 'vz', 'vt', 'vi',
    'adj-i', 'adj-na', 'adj-no', 'adj-t', 'adj-f', 'adj-pn',
    'adv', 'adv-to',
    'exp', 'int', 'conj',
    'n-adv', 'n-t', 'n-suf', 'n-pref',
    'num', 'ctr',
}

# POS tags that are grammatical particles (to filter out)
PARTICLE_POS: Set[str] = {'prt', 'cop', 'aux-v', 'aux-adj'}


class WordResult(BaseModel):
    """
    Pydantic model for a single analyzed word.
    
    This is a simplified, normalized version of WordInfo designed for API responses.
    """
    text: str = Field(..., description="Surface text as it appears in input")
    kana: str = Field(..., description="Kana reading")
    meanings: List[str] = Field(default_factory=list, description="List of English meanings/glosses")
    pos: Optional[str] = Field(None, description="Part of speech (e.g., '[n,vs,vt]')")
    score: int = Field(0, description="Word score (higher = more common/confident)")
    
    # Position info
    start: Optional[int] = Field(None, description="Start index in original text")
    end: Optional[int] = Field(None, description="End index in original text")
    
    # Conjugation info
    is_conjugated: bool = Field(False, description="True if word is a conjugated form")
    source_form: Optional[str] = Field(None, description="Dictionary form if conjugated")
    conj_type: Optional[str] = Field(None, description="Conjugation type (e.g., 'Continuative')")
    is_negative: bool = Field(False, description="True if negative form")
    is_formal: bool = Field(False, description="True if formal/polite form")
    
    # Word type info
    is_compound: bool = Field(False, description="True if compound word")
    word_type: str = Field("kana", description="Word type: 'kanji', 'kana', or 'gap'")
    
    # JMdict reference
    seq: Optional[int] = Field(None, description="JMdict sequence number")
    
    class Config:
        from_attributes = True  # Allow creating from ORM/dataclass objects
    
    @classmethod
    def from_word_info(cls, wi: Any) -> "WordResult":
        """Create WordResult from a WordInfo object."""
        # Normalize kana (can be str or list)
        kana = wi.kana
        if isinstance(kana, list):
            kana = kana[0] if kana else ""
        
        # Normalize seq (can be int or list)
        seq = wi.seq
        if isinstance(seq, list):
            seq = seq[0] if seq else None
        
        return cls(
            text=wi.text,
            kana=kana,
            meanings=wi.meanings if wi.meanings else [],
            pos=wi.pos,
            score=wi.score,
            start=wi.start,
            end=wi.end,
            is_conjugated=bool(wi.conjugations and wi.conjugations != 'root'),
            source_form=wi.source_text,
            conj_type=wi.conj_type,
            is_negative=wi.conj_neg,
            is_formal=wi.conj_fml,
            is_compound=wi.is_compound,
            word_type=wi.type.value if hasattr(wi.type, 'value') else str(wi.type),
            seq=seq,
        )
    
    def is_content_word(self) -> bool:
        """Check if this word is a content word (not a particle/grammatical word)."""
        if not self.pos:
            return False
        # Extract POS tags from "[n,vs,vt]" format
        pos_str = self.pos.strip('[]')
        tags = [t.strip() for t in pos_str.split(',')]
        # Check if any tag is a content word POS
        return any(t in CONTENT_WORD_POS for t in tags)


class AnalysisResult(BaseModel):
    """
    Pydantic model for analysis results.
    
    Contains a list of analyzed words and the overall score.
    """
    words: List[WordResult] = Field(..., description="List of analyzed words")
    score: int = Field(..., description="Overall segmentation score")
    
    @classmethod
    def from_analysis(cls, results: List[tuple]) -> List["AnalysisResult"]:
        """
        Create list of AnalysisResult from himotoki.analyze() output.
        
        Args:
            results: Output from himotoki.analyze() - list of (word_infos, score) tuples
            
        Returns:
            List of AnalysisResult objects
        """
        return [
            cls(
                words=[WordResult.from_word_info(wi) for wi in words],
                score=score
            )
            for words, score in results
        ]
    
    @classmethod
    def from_analysis_single(cls, results: List[tuple]) -> "AnalysisResult":
        """
        Create single AnalysisResult from the best (first) result.
        
        Args:
            results: Output from himotoki.analyze()
            
        Returns:
            Single AnalysisResult for the best segmentation
            
        Raises:
            ValueError: If results is empty
        """
        if not results:
            raise ValueError("No analysis results")
        
        words, score = results[0]
        return cls(
            words=[WordResult.from_word_info(wi) for wi in words],
            score=score
        )


# =============================================================================
# Simplified Vocabulary Models (for language learning apps)
# =============================================================================

class VocabularyItem(BaseModel):
    """
    Simplified vocabulary item for language learning apps.
    
    This is a minimal representation focusing on what learners need:
    - The word as it appears in text
    - Base (dictionary) form
    - Reading in kana
    - Primary meaning
    - Conjugation hint (if applicable)
    """
    word: str = Field(..., description="Word as it appears in text")
    base: str = Field(..., description="Base/dictionary form of the word")
    reading: str = Field(..., description="Reading in hiragana")
    meaning: str = Field(..., description="Primary English meaning")
    conjugation_hint: Optional[str] = Field(
        None, 
        description="Human-readable conjugation explanation (e.g., 'must; have to')"
    )
    
    @classmethod
    def from_word_result(cls, w: WordResult) -> "VocabularyItem":
        """Create VocabularyItem from a WordResult."""
        # Base form: use source_form if conjugated, otherwise the word itself
        base = w.source_form if w.source_form else w.text
        
        # Reading: for conjugated words, we want the base form's reading
        # For now, we use the surface reading (TODO: look up base reading)
        reading = w.kana
        
        # Primary meaning: first meaning or empty
        meaning = w.meanings[0] if w.meanings else ""
        
        # Conjugation hint: generate from conjugation info
        conjugation_hint = None
        if w.is_conjugated and w.conj_type:
            hints = []
            if w.conj_type:
                hints.append(w.conj_type)
            if w.is_negative:
                hints.append("negative")
            if w.is_formal:
                hints.append("formal")
            conjugation_hint = "; ".join(hints) if hints else None
        
        return cls(
            word=w.text,
            base=base,
            reading=reading,
            meaning=meaning,
            conjugation_hint=conjugation_hint,
        )


class VocabularyResult(BaseModel):
    """
    Simplified vocabulary extraction result.
    
    Filters out grammatical particles and returns only content words
    in a format suitable for language learning apps.
    
    Example response:
        {
            "vocabulary": [
                {"word": "日本語", "base": "日本語", "reading": "にほんご", "meaning": "Japanese (language)"},
                {"word": "勉強", "base": "勉強", "reading": "べんきょう", "meaning": "study"},
                {"word": "しなければならない", "base": "する", "reading": "する", "meaning": "to do", "conjugation_hint": "must; have to"}
            ],
            "count": 3
        }
    """
    vocabulary: List[VocabularyItem] = Field(..., description="List of vocabulary items")
    count: int = Field(..., description="Number of vocabulary items")
    
    @classmethod
    def from_analysis(
        cls, 
        results: List[tuple], 
        filter_particles: bool = True,
    ) -> "VocabularyResult":
        """
        Create VocabularyResult from himotoki.analyze() output.
        
        Args:
            results: Output from himotoki.analyze()
            filter_particles: If True, filter out grammatical particles (default True)
            
        Returns:
            VocabularyResult with simplified vocabulary
        """
        if not results:
            return cls(vocabulary=[], count=0)
        
        words, _ = results[0]
        word_results = [WordResult.from_word_info(wi) for wi in words]
        
        # Filter out particles and gaps if requested
        if filter_particles:
            word_results = [
                w for w in word_results 
                if w.word_type != 'gap' and w.is_content_word()
            ]
        else:
            word_results = [w for w in word_results if w.word_type != 'gap']
        
        vocabulary = [VocabularyItem.from_word_result(w) for w in word_results]
        
        return cls(
            vocabulary=vocabulary,
            count=len(vocabulary),
        )


# Aliases for backward compatibility
Word = WordResult
Analysis = AnalysisResult
Vocabulary = VocabularyResult
