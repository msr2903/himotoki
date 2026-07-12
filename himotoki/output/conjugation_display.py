"""
Conjugation display and breakdown tree formatting.
"""

from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from himotoki.db.models import Conjugation, ConjProp, ConjSourceReading
from himotoki.lookup import get_conj_data, get_conj_type_name, get_conj_neg, get_conj_fml, get_source_text
from himotoki.constants import (
    CONJ_TYPE_NAMES, CONJ_STEP_GLOSSES, CONJ_CAUSATIVE, CONJ_CAUSATIVE_PASSIVE,
    get_conj_description,
)
from himotoki.suffixes import get_suffix_description
from himotoki.output.meanings import get_entry_reading
from himotoki.output.types import WordInfo, ConjStep, SUPPRESS_CONJ_FOR_PARTICLES, SUPPRESS_CONJ_FOR_NOUNS, SUPPRESS_CONJ_FOR_VERBS

def _get_conjugation_display(
    session: Session,
    wi: WordInfo,
) -> List[str]:
    """Get conjugation display lines for a WordInfo.
    
    Handles:
    - Single words with DB conjugation chains (via chain → tree)
    - Multi-alternative words (seq is a list)
    - Compound words (show chain for primary component + suffix components)
    
    Returns empty list if word is not conjugated or is a root form.
    """
    if not wi.seq:
        return []
    
    # Compound words: show breakdown for each component that has conjugation
    if wi.is_compound and wi.components:
        return _get_compound_display(session, wi)
    
    # Multi-alternative words where alternatives are compounds
    # (e.g., 食べられていた: alternative=True, components are compound WordInfos)
    if wi.alternative and wi.components:
        primary = wi.components[0]
        if primary.is_compound and primary.components:
            return _get_compound_display(session, primary)

        # Standalone alternatives may have conjugation data only on a
        # non-primary alternative (e.g., だろう/でしょう/ではない). Fall back
        # to the first alternative that carries conjugation metadata.
        for alt in wi.components:
            if alt.conjugations and alt.conjugations != 'root' and alt.seq:
                alt_seq = alt.seq[0] if isinstance(alt.seq, list) else alt.seq
                lines = format_conjugation_info(session, alt_seq, alt.conjugations)
                if wi.text == 'ではない':
                    lines = [line.replace('(じゃない)', '(ではない)') for line in lines]
                return lines
    
    conjugations = wi.conjugations
    if not conjugations or conjugations == 'root':
        return []
    
    # For multi-alternative words (seq is a list), use the first seq
    seq = wi.seq[0] if isinstance(wi.seq, list) else wi.seq
    lines = format_conjugation_info(session, seq, conjugations)
    if wi.text == 'ではない':
        lines = [line.replace('(じゃない)', '(ではない)') for line in lines]
    return lines


def _get_compound_display(
    session: Session,
    wi: WordInfo,
) -> List[str]:
    """Get conjugation display for a compound word.
    
    Shows the primary component's conjugation chain, then lists
    each suffix component on subsequent tree lines.
    
    Special handling:
    - する is absorbed into a ← root line (勉強する instead of └─ する)
    - いる/おる after て are hidden; て is relabeled as progressive
    
    Example for 勉強しています (4→2 levels):
      ← 勉強する 【べんきょうする】
      └─ Conjunctive (~te, progressive) (て)
           └─ Polite (ます)
    
    Example for 書かせられていた:
      ← 書く【かく】
      └─ Causative-Passive (書かせられる): is made to do
           └─ Conjunctive (~te, progressive) (て)
                └─ Past (~ta) (た): did/was
    """
    result = []
    
    if not wi.components:
        return result
    
    primary = wi.components[0]
    
    # Get the primary component's conjugation chain
    primary_chain = []
    if primary.conjugations and primary.conjugations != 'root' and primary.seq:
        primary_seq = primary.seq[0] if isinstance(primary.seq, list) else primary.seq
        primary_chain = format_conjugation_info(session, primary_seq, primary.conjugations)
    
    if primary_chain:
        result.extend(primary_chain)
    
    # Count existing tree depth from primary chain
    depth = 0
    for line in primary_chain:
        stripped = line.lstrip()
        if stripped.startswith("└─"):
            depth += 1
    
    # Add remaining components as continuation of the tree
    for comp in wi.components[1:]:
        indent = "     " * depth
        comp_kana = comp.kana if isinstance(comp.kana, str) else (comp.kana[0] if comp.kana else comp.text)
        # Fallback to text if kana is empty (e.g., abbreviation-based suffixes like もいい)
        if not comp_kana:
            comp_kana = comp.text
        comp_seq = comp.seq[0] if isinstance(comp.seq, list) else comp.seq if comp.seq else None
        
        # Get suffix description for this component
        desc = get_suffix_description(comp_seq, text=comp_kana) if (comp_seq or comp_kana) else None
        desc_str = f" ({desc})" if desc else ""

        # na-adjective copula compounds (静かでした, 大丈夫です)
        if not primary_chain and depth == 0 and comp_kana in ('です', 'でした'):
            primary_kana = primary.kana if isinstance(primary.kana, str) else (primary.kana[0] if primary.kana else primary.text)
            if primary.text and primary.text != primary_kana:
                result.append(f"  ← {primary.text}だ 【{primary_kana}だ】")
            else:
                result.append(f"  ← {primary_kana}だ")

            result.append("  └─ Polite (です)")
            depth = 1

            if comp_kana == 'でした':
                result.append("       └─ Past (~ta) (でした): did/was")
                depth = 2
            continue

        # i-adj + すぎる compounds may arrive without explicit conjugation IDs
        # on the primary component (e.g., 高すぎる). In that case, synthesize
        # the source + adjective stem steps for readability.
        if not primary_chain and depth == 0 and comp_kana == "すぎる":
            primary_kana = primary.kana if isinstance(primary.kana, str) else (primary.kana[0] if primary.kana else primary.text)
            if primary_kana and primary_kana.endswith("い"):
                primary_seq = primary.seq[0] if isinstance(primary.seq, list) else primary.seq
                if primary_seq:
                    result.append(f"  ← {get_entry_reading(session, primary_seq)}")
                stem_kana = primary_kana[:-1]
                result.append(f"  └─ Adjective Stem ({stem_kana}): stem")
                depth = 1
                indent = "     " * depth
        
        if comp.conjugations and comp.conjugations != 'root' and comp.seq:
            # This suffix component is itself conjugated (e.g., いた = past of いる)
            comp_chain = format_conjugation_info(session, comp_seq, comp.conjugations)
            if comp_chain:
                # Extract auxiliary verb name from root line
                aux_name = _extract_aux_name_from_chain(comp_chain)
                
                if aux_name == "する" and not primary_chain:
                    # ABSORB する: show ← noun+する root line
                    primary_kana = primary.kana if isinstance(primary.kana, str) else (primary.kana[0] if primary.kana else primary.text)
                    if primary.text and primary.text != primary_kana:
                        result.append(f"  ← {primary.text}する 【{primary_kana}する】")
                    else:
                        result.append(f"  ← {primary_kana}する")
                    # Add する's conjugation children (skip the ← root line)
                    for line in comp_chain[1:]:
                        stripped = line.lstrip()
                        if stripped.startswith("└─"):
                            sub_indent = "     " * depth
                            result.append(f"  {sub_indent}{stripped}")
                            depth += 1
                
                elif aux_name in ("いる", "おる") and _last_line_is_te(result):
                    # HIDE いる/おる: relabel て as progressive, promote children
                    _relabel_te_progressive(result)
                    # Add いる/おる's conjugation children (skip the ← root line)
                    for line in comp_chain[1:]:
                        stripped = line.lstrip()
                        if stripped.startswith("└─"):
                            sub_indent = "     " * depth
                            result.append(f"  {sub_indent}{stripped}")
                            depth += 1
                
                else:
                    # Normal: merge sub-chain into tree
                    for line in comp_chain:
                        stripped = line.lstrip()
                        if stripped.startswith("←"):
                            sub_indent = "     " * depth
                            result.append(f"  {sub_indent}└─ {aux_name}{desc_str}")
                            depth += 1
                        elif stripped.startswith("└─"):
                            sub_indent = "     " * depth
                            result.append(f"  {sub_indent}{stripped}")
                            depth += 1
            else:
                result.append(f"  {indent}└─ {comp_kana}{desc_str}")
                depth += 1
        else:
            # Unconjugated suffix component
            if comp_kana == "する" and not primary_chain:
                # ABSORB unconjugated する: show ← noun+する root line
                primary_kana = primary.kana if isinstance(primary.kana, str) else (primary.kana[0] if primary.kana else primary.text)
                if primary.text and primary.text != primary_kana:
                    result.append(f"  ← {primary.text}する 【{primary_kana}する】")
                else:
                    result.append(f"  ← {primary_kana}する")
            elif comp_kana in ("いる", "おる") and _last_line_is_te(result):
                # HIDE unconjugated いる/おる: relabel て as progressive
                _relabel_te_progressive(result)
            else:
                result.append(f"  {indent}└─ {comp_kana}{desc_str}")
                depth += 1
    
    return result


def _extract_aux_name_from_chain(comp_chain: List[str]) -> Optional[str]:
    """Extract the auxiliary verb kana name from a conjugation chain's root line.
    
    Given a chain like ["  ← 為る 【する】", "  └─ Past (~ta) (た)"],
    returns "する" (the kana inside 【...】).
    """
    if not comp_chain:
        return None
    first = comp_chain[0].lstrip()
    if not first.startswith("←"):
        return None
    aux_name = first[2:].strip()
    if "【" in aux_name and "】" in aux_name:
        start = aux_name.index("【") + 1
        end = aux_name.index("】")
        return aux_name[start:end]
    return aux_name


def _last_line_is_te(result: List[str]) -> bool:
    """Check if the last tree line contains Conjunctive (~te)."""
    for line in reversed(result):
        stripped = line.lstrip()
        if stripped.startswith("└─") and "Conjunctive (~te" in stripped:
            return True
        if stripped.startswith("└─") or stripped.startswith("←"):
            return False
    return False


def _relabel_te_progressive(result: List[str]) -> None:
    """Find the last Conjunctive (~te) line and relabel it as progressive."""
    for i in range(len(result) - 1, -1, -1):
        if "Conjunctive (~te)" in result[i]:
            result[i] = result[i].replace(
                "Conjunctive (~te)",
                "Conjunctive (~te, progressive)",
            )
            return


def format_conjugation_info(
    session: Session,
    seq: int,
    conjugations: List[int],
) -> List[str]:
    """Format conjugation info as text lines with breakdown tree.
    
    For simple conjugations (no via chain), shows the classic bracket format
    plus a single-step tree. For multi-step conjugations (via chains),
    shows a full derivation tree with box-drawing characters.
    """
    result = []
    
    query = select(Conjugation).where(Conjugation.seq == seq)
    if conjugations:
        query = query.where(Conjugation.id.in_(conjugations))
    
    conjs = session.execute(query).scalars().all()
    
    # Use only the first (primary) conjugation to avoid showing
    # duplicate trees from archaic/variant analyses (e.g., 忘れる vs 忘る)
    for conj in conjs[:1]:
        props = session.execute(
            select(ConjProp).where(ConjProp.conj_id == conj.id)
        ).scalars().all()
        
        for prop in props[:1]:
            # Build the full conjugation chain (innermost first)
            steps = _build_conj_chain(session, conj, prop)
            
            if steps:
                # Show tree breakdown
                root_reading = get_entry_reading(session, conj.from_seq)
                result.append(f"  ← {root_reading}")
                current_depth = 0
                for step in steps:
                    indent = "     " * current_depth
                    if step.conj_type == "Causative-Passive":
                        # Split into two separate steps: Causative then Passive
                        suffix = step.suffix
                        caus_suffix = suffix
                        pass_suffix = ""
                        if "られ" in suffix:
                            idx = suffix.index("られ")
                            caus_suffix = suffix[:idx]
                            pass_suffix = suffix[idx:]
                        elif "され" in suffix:
                            idx = suffix.index("され")
                            caus_suffix = suffix[:idx + 1]  # include さ
                            pass_suffix = suffix[idx + 1:]  # れる
                        result.append(f"  {indent}└─ Causative ({caus_suffix}): makes do")
                        current_depth += 1
                        indent = "     " * current_depth
                        if pass_suffix:
                            result.append(f"  {indent}└─ Passive ({pass_suffix}): is done (to)")
                        else:
                            result.append(f"  {indent}└─ Passive: is done (to)")
                        current_depth += 1
                    elif step.fml:
                        # Show Polite as its own tree step
                        polite_morpheme = "です" if step.suffix.startswith("で") else "ます"
                        result.append(f"  {indent}└─ Polite ({polite_morpheme})")
                        current_depth += 1
                        # If there's an actual conjugation beyond plain polite non-past
                        if step.conj_type != "Non-past" or step.neg:
                            indent = "     " * current_depth
                            # Extract post-masu suffix
                            # ました→した, ません→せん
                            suffix = step.suffix
                            if step.conj_type == "Volitional":
                                # Use abstract volitional morpheme よう
                                # (neutral, stackable on any verb)
                                suffix = "よう"
                            elif "ま" in suffix:
                                idx = suffix.index("ま")
                                suffix = suffix[idx + 1:]  # strip ま, keep した/せん
                            if step.neg:
                                if step.conj_type == "Non-past":
                                    # Polite negative: せん → Negative (せん)
                                    result.append(f"  {indent}└─ Negative ({suffix}): not")
                                    current_depth += 1
                                elif suffix.startswith("せん") and len(suffix) > 2:
                                    # Polite neg + conjugation: せんでした
                                    # → Negative (せん) + Past (でした)
                                    conj_suffix = suffix[2:]
                                    result.append(f"  {indent}└─ Negative (せん): not")
                                    current_depth += 1
                                    indent = "     " * current_depth
                                    gloss_str = f": {step.gloss}" if step.gloss else ""
                                    result.append(f"  {indent}└─ {step.conj_type} ({conj_suffix}){gloss_str}")
                                    current_depth += 1
                                else:
                                    # Fallback for other formal neg patterns
                                    neg_part, conj_part = _split_neg_suffix(suffix)
                                    result.append(f"  {indent}└─ Negative ({neg_part}): not")
                                    current_depth += 1
                                    if conj_part:
                                        indent = "     " * current_depth
                                        gloss_str = f": {step.gloss}" if step.gloss else ""
                                        result.append(f"  {indent}└─ {step.conj_type} ({conj_part}){gloss_str}")
                                        current_depth += 1
                            else:
                                label = step.conj_type
                                gloss_str = f": {step.gloss}" if step.gloss else ""
                                result.append(f"  {indent}└─ {label} ({suffix}){gloss_str}")
                                current_depth += 1
                    else:
                        type_label = step.conj_type
                        gloss = step.gloss
                        suffix = step.suffix
                        if type_label == "Potential":
                            # Show dual label only when form is ambiguous
                            # Godan potential starts with え-dan kana (け,せ,て,...)
                            # which is clearly just Potential. Only れ/られ forms
                            # (ichidan verbs) are ambiguous with Passive.
                            _GODAN_POTENTIAL = set("えけせてねへめげ")
                            first_char = suffix[0] if suffix else ""
                            if first_char not in _GODAN_POTENTIAL:
                                type_label = "Potential/Passive"
                                gloss = "can do / is done (to)"
                        if step.neg:
                            # Split negative into separate tree levels
                            if type_label == "Non-past":
                                # Pure negative: ない is the non-past neg form
                                result.append(f"  {indent}└─ Negative ({suffix}): not")
                                current_depth += 1
                            elif suffix.endswith("ない"):
                                # Type + Negative: type applied first, then negated
                                # e.g., けない → Potential (け) + Negative (ない)
                                conj_suffix = suffix[:-2]
                                gloss_str = f": {gloss}" if gloss else ""
                                result.append(f"  {indent}└─ {type_label} ({conj_suffix}){gloss_str}")
                                current_depth += 1
                                indent = "     " * current_depth
                                result.append(f"  {indent}└─ Negative (ない): not")
                                current_depth += 1
                            else:
                                # Negative + conjugation: negated first, then ない conjugated
                                # e.g., なかった → Negative (ない) + Past (かった)
                                neg_part, conj_part = _split_neg_suffix(suffix)
                                result.append(f"  {indent}└─ Negative ({neg_part}): not")
                                current_depth += 1
                                if conj_part:
                                    indent = "     " * current_depth
                                    gloss_str = f": {gloss}" if gloss else ""
                                    result.append(f"  {indent}└─ {type_label} ({conj_part}){gloss_str}")
                                    current_depth += 1
                        else:
                            gloss_str = f": {gloss}" if gloss else ""
                            result.append(f"  {indent}└─ {type_label} ({suffix}){gloss_str}")
                            current_depth += 1
            else:
                # Fallback: flat format for cases where chain can't be built
                neg_str = ' Negative' if prop.neg else ' Affirmative'
                fml_str = ' Formal' if prop.fml else ' Plain'
                type_desc = get_conj_description(prop.conj_type)
                result.append(f"  ← [{prop.pos}] {type_desc}{neg_str}{fml_str}")
                result.append(f"     {get_entry_reading(session, conj.from_seq)}")
    
    return result


def _build_conj_chain(
    session: Session,
    conj: Conjugation,
    outer_prop: ConjProp,
) -> List[ConjStep]:
    """
    Walk a conjugation's via chain and build an ordered list of ConjSteps.
    
    The chain goes from the root outward:
    e.g., for 食べられなかった (eat+passive+neg+past):
      root: 食べる
      step 1: Passive (られる) - from via chain  
      step 2: Past (neg=True) - from outer prop
    
    For 行きました (go+polite+past):
      root: 行く
      step 1: Past (た) - single step (fml=True)
    
    Negative is stored as a flag on ConjStep.neg; the renderer splits
    it into a separate "Negative" tree node at display time.
    """
    from himotoki.lookup import get_conj_data
    
    steps = []
    
    if conj.via is not None:
        # Multi-step conjugation: walk the via chain from inside out
        _collect_via_steps(session, conj.via, conj.from_seq, steps)
    
    # Add the outermost conjugation step
    type_name = CONJ_TYPE_NAMES.get(outer_prop.conj_type, f"Type {outer_prop.conj_type}")
    gloss = CONJ_STEP_GLOSSES.get(outer_prop.conj_type, "")
    
    # Get the suffix text: difference between conjugated text and source text
    suffix = _get_conj_suffix(session, conj, outer_prop)
    
    steps.append(ConjStep(
        conj_type=type_name,
        suffix=suffix,
        gloss=gloss,
        neg=bool(outer_prop.neg),
        fml=bool(outer_prop.fml),
    ))
    
    return steps


def _collect_via_steps(
    session: Session,
    via_seq: int,
    from_seq: int,
    steps: List[ConjStep],
) -> None:
    """
    Recursively collect conjugation steps from a via chain.
    
    Walks from the innermost via to the outermost, appending steps in order.
    """
    from himotoki.lookup import get_conj_data
    
    via_data = get_conj_data(session, via_seq, from_seq=from_seq)
    if not via_data:
        return
    
    cd = via_data[0]
    
    # If this via has its own via, recurse deeper first
    if cd.via is not None:
        _collect_via_steps(session, cd.via, cd.from_seq, steps)
    
    # Now add this step
    if cd.prop:
        type_name = CONJ_TYPE_NAMES.get(cd.prop.conj_type, f"Type {cd.prop.conj_type}")
        gloss = CONJ_STEP_GLOSSES.get(cd.prop.conj_type, "")
        
        # Get suffix text from src_map
        # Pick the reading that gives the shortest non-empty suffix
        # to avoid variant kanji (e.g., 喰べ for 食べ) breaking extraction
        # Exception: Causative types prefer longest suffix:
        # - Causative: standard させる over dialectal さす
        # - Causative-Passive: full かせられる splits cleanly into かせ + られる
        prefer_long = cd.prop.conj_type in (CONJ_CAUSATIVE, CONJ_CAUSATIVE_PASSIVE)
        suffix = ""
        if cd.src_map:
            best_suffix = None
            for text, src in cd.src_map:
                s = _extract_suffix(text, src)
                if s and s != text:  # real match (not fallback to full text)
                    if best_suffix is None:
                        best_suffix = s
                    elif prefer_long and len(s) > len(best_suffix):
                        best_suffix = s
                    elif not prefer_long and len(s) < len(best_suffix):
                        best_suffix = s
            
            if best_suffix is not None:
                suffix = best_suffix
            else:
                # Fallback: use first reading
                suffix = _extract_suffix(cd.src_map[0][0], cd.src_map[0][1])
        
        steps.append(ConjStep(
            conj_type=type_name,
            suffix=suffix,
            gloss=gloss,
            neg=bool(cd.prop.neg),
            fml=bool(cd.prop.fml),
        ))


def _get_conj_suffix(
    session: Session,
    conj: Conjugation,
    prop: ConjProp,
) -> str:
    """
    Get the suffix text that represents this conjugation step.
    
    Uses ConjSourceReading to find the conjugated form, then extracts
    the part that differs from the source.
    """
    src_readings = session.execute(
        select(ConjSourceReading).where(ConjSourceReading.conj_id == conj.id)
    ).scalars().all()
    
    if not src_readings:
        return ""
    
    # Pick the reading that gives the best suffix.
    # Usually shortest non-empty to avoid variant kanji breaking extraction.
    # Exception: Causative types prefer longest (standard form over dialectal).
    prefer_long = prop.conj_type in (CONJ_CAUSATIVE, CONJ_CAUSATIVE_PASSIVE)
    best_suffix = None
    for sr in src_readings:
        suffix = _extract_suffix(sr.text, sr.source_text)
        if suffix and suffix != sr.text:  # suffix != full text means we found a real match
            if best_suffix is None:
                best_suffix = suffix
            elif prefer_long and len(suffix) > len(best_suffix):
                best_suffix = suffix
            elif not prefer_long and len(suffix) < len(best_suffix):
                best_suffix = suffix
    
    if best_suffix is not None:
        return best_suffix
    
    # Fallback: use first reading
    return _extract_suffix(src_readings[0].text, src_readings[0].source_text)


def _split_neg_suffix(suffix: str) -> Tuple[str, str]:
    """Split a negative conjugation suffix into (neg_part, conj_part).
    
    The negative marker ない conjugates like an i-adjective, so negative
    suffixes contain the neg marker plus its own conjugation ending.
    
    Examples:
        なかった → (ない, かった)     # neg + past
        まなかった → (まない, かった)  # neg + past (godan)
        くなかった → (くない, かった)  # neg + past (i-adj)
        なくて → (ない, くて)          # neg + te
        なければ → (ない, ければ)      # neg + provisional
        ないで → (ない, で)            # neg + te (variant)
        ない → (ない, "")              # just negative
    """
    # ない-conjugation endings (most specific first to avoid partial matches)
    for ending in ("かったら", "かった", "ければ", "くて"):
        if suffix.endswith(ending):
            neg_part = suffix[:-len(ending)] + "い"
            return neg_part, ending
    
    # ないで pattern (negative te-form variant)
    if suffix.endswith("で") and len(suffix) >= 3:
        potential_neg = suffix[:-1]
        if potential_neg.endswith("ない"):
            return potential_neg, "で"
    
    # No further conjugation (e.g., just ない)
    return suffix, ""


def _extract_suffix(conj_text: str, src_text: str) -> str:
    """
    Extract the changed suffix by comparing conjugated and source text.
    
    e.g., (食べられなかった, 食べられる) → なかった
          (食べられる, 食べる) → られる (replace る with られる)
          (行きました, 行く) → きました
    """
    # Find common prefix
    common_len = 0
    for i, (c1, c2) in enumerate(zip(conj_text, src_text)):
        if c1 == c2:
            common_len = i + 1
        else:
            break
    
    suffix_part = conj_text[common_len:]
    return suffix_part if suffix_part else conj_text
