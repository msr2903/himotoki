#!/usr/bin/env python3
"""
Comprehensive audit of Japanese grammatical form display in himotoki.

Tests every major auxiliary verb / grammatical suffix pattern to verify
the conjugation chain correctly shows intermediate grammatical steps.

Japanese Grammar Reference (organized by category):
=====================================================

A. TE-FORM AUXILIARIES (V-te + auxiliary verb)
   1. ~ている/~てる        progressive/resultative
   2. ~ていく/~てく        action continuing forward
   3. ~てくる             action continuing toward speaker
   4. ~てしまう/~ちゃう    completion/regret
   5. ~ておく/~とく       do in advance/preparation
   6. ~てみる             try doing
   7. ~てあげる           do for someone (giving up)
   8. ~てもらう           receive an action done for you
   9. ~てくれる           receive an action (toward speaker)
   10. ~てある            resultative state (transitive)
   11. ~てほしい          want someone to do

B. CONJUGATED FORMS (single-word inflection via DB)
   12. ~ない              negative
   13. ~た/~だ            past tense
   14. ~ます              polite
   15. ~て/~で            conjunctive/te-form
   16. ~たい              desiderative (want to)
   17. ~れる/~られる      passive
   18. ~せる/~させる      causative
   19. ~れる/~られる      potential
   20. ~(よ)う            volitional
   21. ~ろ/~なさい        imperative
   22. ~ば                provisional
   23. ~たら              conditional

C. COMPLEX GRAMMATICAL PATTERNS (multi-suffix chains)
   24. ~てしまった        te + shimau + past
   25. ~ちゃった          contraction of above
   26. ~ている + past     te-iru + past = teita
   27. ~ていく + past     te-iku + past = teitta
   28. ~ておいた          te-oku + past
   29. ~てみた            te-miru + past
   30. ~させられる        causative-passive
   31. ~なければならない   must do
   32. ~なくてもいい       don't have to
   33. ~ないでください     please don't

D. COPULA & AUXILIARY ADJECTIVE PATTERNS
   34. ~だ/~です          copula
   35. ~そうだ            hearsay / appearance
   36. ~ようだ            resemblance
   37. ~らしい            seems like
   38. ~はずだ            should be / expected

E. COMPOUND VERB PATTERNS
   39. ~始める            begin to
   40. ~終わる            finish doing
   41. ~続ける            continue doing
   42. ~過ぎる            do too much
   43. ~合う              do together/mutually
   44. ~出す              start doing / burst out
"""

import subprocess
import json
import sys

def run_himotoki(text, mode="-j"):
    """Run himotoki and return parsed output."""
    result = subprocess.run(
        ["python", "-m", "himotoki", mode, text],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {"error": result.stderr}
    if mode == "-j":
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"error": f"JSON parse failed: {result.stdout[:200]}"}
    return {"text": result.stdout}


def run_himotoki_full(text):
    """Run himotoki with -f flag and return text output."""
    result = subprocess.run(
        ["python", "-m", "himotoki", "-f", text],
        capture_output=True, text=True
    )
    return result.stdout


def extract_chain_info(json_data):
    """Extract conjugation chain information from JSON output."""
    if not json_data or isinstance(json_data, dict):
        return []
    
    results = []
    # JSON format: [[[romanized, {segment_data}, []], ...], score]
    for segmentation in json_data:
        segments = segmentation[0] if segmentation else []
        for seg_tuple in segments:
            if len(seg_tuple) < 2:
                continue
            seg = seg_tuple[1]
            if not isinstance(seg, dict):
                continue
            
            info = {
                "text": seg.get("text", ""),
                "kana": seg.get("kana", ""),
                "is_compound": seg.get("compound") is not None,
                "compound_parts": seg.get("compound", []),
                "components": [],
                "conj": seg.get("conj", []),
                "source": None,
            }
            
            # Extract source/dictionary form from conj
            if info["conj"]:
                for c in info["conj"]:
                    reading = c.get("reading", "")
                    if reading:
                        info["source"] = reading
                    props = c.get("prop", [])
                    for p in props:
                        info["components"].append({
                            "type": p.get("type", ""),
                            "pos": p.get("pos", ""),
                            "neg": p.get("neg", False),
                            "fml": p.get("fml", False),
                        })
            
            # Extract component info for compounds
            if seg.get("components"):
                comp_info = []
                for comp in seg["components"]:
                    ci = {
                        "text": comp.get("text", ""),
                        "kana": comp.get("kana", ""),
                        "seq": comp.get("seq"),
                        "conj": comp.get("conj", []),
                    }
                    comp_info.append(ci)
                info["comp_detail"] = comp_info
            
            results.append(info)
    return results


# =============================================================================
# Test cases
# =============================================================================

test_cases = [
    # Category A: TE-FORM AUXILIARIES
    # -----------------------------------------------------------------------
    
    # A1: ~ている (progressive)
    ("食べている", 
     "V-te + iru (progressive)", 
     "食べる → te-form → いる (progressive/state)"),
    
    # A1b: ~てる (contracted progressive)
    ("食べてる",
     "V-te + ru (contracted progressive)",
     "食べる → te-form → いる (progressive, contracted)"),
    
    # A2: ~ていく (continuing forward)
    ("変わっていく",
     "V-te + iku (continuing forward)",
     "変わる → te-form → いく (gradual change going forward)"),
    
    # A2b: ~てく (contracted)
    ("変わってく",
     "V-te + ku (contracted continuing forward)",
     "変わる → te-form → いく (contracted)"),
    
    # A3: ~てくる (continuing toward speaker)
    ("寒くなってくる",
     "V-te + kuru (toward speaker)",
     "寒くなる → te-form → くる (change approaching speaker)"),
    
    # A4: ~てしまう (completion/regret)
    ("飲んでしまう",
     "V-te + shimau (completion/regret)",
     "飲む → te-form → しまう (unintentional completion/regret)"),
    
    # A4b: ~ちゃう (contracted shimau)
    ("飲んじゃう",
     "V-te + jau (contracted shimau)",
     "飲む → te-form → しまう→ちゃう (contracted completion)"),
    
    # A4c: ~てしまった (shimau + past)
    ("飲んでしまった",
     "V-te + shimatta (completion past)",
     "飲む → te-form → しまう (completion) → past"),
    
    # A4d: ~ちゃった (contracted shimau + past)
    ("飲んじゃった",
     "V-te + jatta (contracted shimau past)",
     "飲む → te-form → しまう→ちゃう (contracted) → past"),
    
    # A5: ~ておく (preparation)
    ("準備しておく",
     "V-te + oku (preparation/in advance)",
     "準備する → te-form → おく (do in advance)"),
    
    # A5b: ~とく (contracted oku)
    ("やっとく",
     "V-te + toku (contracted preparation)",
     "やる → te-form → おく→とく (contracted in advance)"),
    
    # A6: ~てみる (try doing)
    ("食べてみる",
     "V-te + miru (try doing)",
     "食べる → te-form → みる (try)"),
    
    # A6b: ~てみた (try + past)
    ("食べてみた",
     "V-te + mita (tried doing)",
     "食べる → te-form → みる (try) → past"),
    
    # A7: ~てあげる (do for someone, giving)
    ("教えてあげる",
     "V-te + ageru (do for someone)",
     "教える → te-form → あげる (do for someone/give)"),
    
    # A8: ~てもらう (receive action)
    ("手伝ってもらう",
     "V-te + morau (receive help)",
     "手伝う → te-form → もらう (receive action done for you)"),
    
    # A9: ~てくれる (receive action, toward speaker)
    ("助けてくれる",
     "V-te + kureru (kindly do for me)",
     "助ける → te-form → くれる (do for speaker/in-group)"),
    
    # A10: ~てある (resultative state)
    ("書いてある",
     "V-te + aru (resultative)",
     "書く → te-form → ある (result state exists)"),
    
    # A11: ~てほしい (want someone to do)
    ("来てほしい",
     "V-te + hoshii (want someone to do)",
     "来る → te-form → ほしい (want someone to do)"),
    
    # Category B: SINGLE CONJUGATED FORMS (DB-based)
    # -----------------------------------------------------------------------
    
    # B12: ~ない (negative)
    ("食べない",
     "Negative (nai)",
     "食べる → ない (negative)"),
    
    # B13: ~た (past)
    ("食べた",
     "Past (ta)",
     "食べる → た (past)"),
    
    # B14: ~ます (polite)
    ("食べます",
     "Polite (masu)",
     "食べる → ます (polite)"),
    
    # B15: ~て (te-form)
    ("食べて",
     "Te-form (conjunctive)",
     "食べる → て (conjunctive)"),
    
    # B16: ~たい (desiderative)
    ("食べたい",
     "Desiderative (tai)",
     "食べる → たい (want to)"),
    
    # B17: ~れる/~られる (passive)
    ("食べられる",
     "Passive (rareru)",
     "食べる → られる (passive)"),
    
    # B18: ~させる (causative)
    ("食べさせる",
     "Causative (saseru)",
     "食べる → させる (causative/make do)"),
    
    # B19: potential (same morpheme as passive for ichidan)
    ("走れる",
     "Potential (reru)",
     "走る → れる (potential/can do)"),
    
    # B20: ~よう (volitional)
    ("食べよう",
     "Volitional (you)",
     "食べる → よう (let's/volitional)"),
    
    # B20b: godan volitional
    ("行こう",
     "Volitional godan (ou)",
     "行く → こう (let's go/volitional)"),
    
    # B21: imperative
    ("食べろ",
     "Imperative (ro)",
     "食べる → ろ (imperative: eat!)"),
    
    # B22: ~ば (provisional)
    ("食べれば",
     "Provisional (ba)",
     "食べる → ば (if)"),
    
    # B23: ~たら (conditional)
    ("食べたら",
     "Conditional (tara)",
     "食べる → たら (if/when)"),
    
    # Category C: COMPLEX CHAINS
    # -----------------------------------------------------------------------
    
    # C24: passive + past
    ("食べられた",
     "Passive + past",
     "食べる → られる (passive) → た (past)"),
    
    # C25: causative + passive
    ("食べさせられる",
     "Causative-passive",
     "食べる → させる (causative) → られる (passive)"),
    
    # C26: negative + past
    ("食べなかった",
     "Negative + past",
     "食べる → ない (negative) → かった (past)"),
    
    # C27: polite + past
    ("食べました",
     "Polite + past",
     "食べる → ます (polite) → た (past)"),
    
    # C28: polite + negative
    ("食べません",
     "Polite + negative",
     "食べる → ます (polite) → ん (negative)"),
    
    # C29: polite + negative + past
    ("食べませんでした",
     "Polite + negative + past",
     "食べる → ます (polite) → ん (neg) → でした (past)"),
    
    # C30: te-form + iru + past (was doing)
    ("食べていた",
     "Progressive + past",
     "食べる → て → いる (progressive) → た (past)"),
    
    # C31: te-form + shimau + past
    ("食べてしまった",
     "Shimau + past (regret, completed in past)",
     "食べる → て → しまう (completion) → た (past)"),
    
    # C31b: contracted version
    ("食べちゃった",
     "Contracted shimau + past",
     "食べる → て→ちゃう (contracted shimau) → た (past)"),
    
    # C32: causative + passive + past
    ("食べさせられた",
     "Causative-passive + past",
     "食べる → させ (causative) → られ (passive) → た (past)"),
    
    # C33: potential + negative
    ("食べられない",
     "Potential + negative",
     "食べる → られる (potential) → ない (negative)"),
    
    # C34: desiderative + past
    ("食べたかった",
     "Desiderative + past",
     "食べる → たい (want to) → かった (past)"),
    
    # C35: desiderative + negative
    ("食べたくない",
     "Desiderative + negative",
     "食べる → たい (want to) → ない (negative)"),
    
    # C36: -nakya (must do, contraction)
    ("食べなきゃ",
     "Must do (contraction of nakereba)",
     "食べる → ない → なければ → なきゃ (must)"),
    
    # C37: te-oku + past  
    ("準備しておいた",
     "Te-oku + past (prepared in advance)",
     "準備する → て → おく (in advance) → た (past)"),
    
    # Category D: COPULA & AUXILIARIES
    # -----------------------------------------------------------------------
    
    # D34: copula
    ("静かだ",
     "Na-adj + copula da",
     "静か + だ (copula)"),
    
    # D34b: polite copula
    ("静かです",
     "Na-adj + polite copula",
     "静か + です (polite copula)"),
    
    # D35: ~そうだ (appearance)
    ("降りそうだ",
     "Sou da (looks like)",
     "降る → そう (appears to) + だ"),
    
    # D36: ~ようだ (resemblance)
    ("雨のようだ",
     "You da (seems like)",
     "雨 + のようだ (seems like rain)"),
    
    # D37: ~らしい (seems like)
    ("雨らしい",
     "Rashii (seems like)",
     "雨 + らしい (it seems)"),
    
    # Category E: COMPOUND VERBS
    # -----------------------------------------------------------------------
    
    # E39: ~始める (begin)
    ("食べ始める",
     "V-stem + hajimeru (begin to)",
     "食べる → 食べ始める (begin eating)"),
    
    # E40: ~終わる (finish)
    ("食べ終わる",
     "V-stem + owaru (finish)",
     "食べる → 食べ終わる (finish eating)"),
    
    # E41: ~続ける (continue)
    ("食べ続ける",
     "V-stem + tsuzukeru (continue)",
     "食べる → 食べ続ける (continue eating)"),
    
    # E42: ~過ぎる (too much)
    ("食べ過ぎる",
     "V-stem + sugiru (too much)",
     "食べる → 食べ過ぎる (eat too much)"),
    
    # E42b: sugiru + past
    ("食べ過ぎた",
     "V-stem + sugiru + past",
     "食べる → 食べ過ぎる (too much) → た (past)"),
    
    # E43: ~合う (together/mutually)
    ("話し合う",
     "V-stem + au (mutually)",
     "話す → 話し合う (discuss together)"),
    
    # E44: ~出す (burst out)
    ("泣き出す",
     "V-stem + dasu (burst out)",
     "泣く → 泣き出す (burst out crying)"),
    
    # EXTRA: Godan verbs with different stems
    # -----------------------------------------------------------------------
    
    ("走った",
     "Godan -ru past",
     "走る → った (past)"),
    
    ("書いた",
     "Godan -ku past",
     "書く → いた (past)"),
    
    ("泳いだ",
     "Godan -gu past",
     "泳ぐ → いだ (past)"),
    
    ("飲んだ",
     "Godan -mu past",
     "飲む → んだ (past)"),
    
    ("死んだ",
     "Godan -nu past",
     "死ぬ → んだ (past)"),
    
    ("遊んだ",
     "Godan -bu past",
     "遊ぶ → んだ (past)"),
    
    ("話した",
     "Godan -su past",
     "話す → した (past)"),
    
    ("待った",
     "Godan -tsu past",
     "待つ → った (past)"),
    
    ("行った",
     "Godan iku irregular past",
     "行く → った (past, irregular: いった not いいた)"),
    
    # Irregular verbs
    ("した",
     "Suru irregular past",
     "する → した (past)"),
    
    ("来た",
     "Kuru irregular past",
     "来る → た (past, reading: きた)"),
    
    # Special patterns
    ("行ってきた",
     "Itte-kita (went and came back)",
     "行く → て-form → くる (came back) → た (past)"),
    
    ("やっていける",
     "V-te + ikeru (can manage)",
     "やる → て → いく (forward) → potential"),
    
    ("勉強させてもらう",
     "Causative + te + morau",
     "勉強する → させる (causative) → て → もらう (receive)"),
]


def main():
    print("=" * 80)
    print("HIMOTOKI JAPANESE GRAMMAR AUDIT")
    print("=" * 80)
    print(f"\nTesting {len(test_cases)} grammatical patterns...\n")
    
    issues = []
    
    for i, (text, label, expected) in enumerate(test_cases, 1):
        full_output = run_himotoki_full(text)
        json_data = run_himotoki(text, "-j")
        
        # Check for problems
        has_issue = False
        issue_notes = []
        
        # Extract key info from full output
        lines = full_output.strip().split('\n')
        
        # Look for conjugation chain lines (└─ lines)
        chain_lines = [l.strip() for l in lines if '└─' in l or '← ' in l]
        
        # Look for component display
        comp_lines = [l.strip() for l in lines if l.strip().startswith('└─')]
        
        # Check if compound parts are shown vs conjugation chain
        has_conj_chain = any('└─' in l and ('(' in l or '←' in l) for l in lines)
        has_source = any('←' in l for l in lines)
        
        # For te-form auxiliaries (category A), check if the auxiliary verb is shown
        if label.startswith("V-te"):
            # These should show the auxiliary verb in the chain
            # Check if it's just showing te-form + past without the auxiliary
            chain_text = ' '.join(chain_lines)
            
            # Check for shimau/ちゃう visibility
            if "shimau" in label.lower() or "jau" in label.lower() or "しまう" in expected:
                if "しまう" not in chain_text and "ちゃう" not in chain_text and "じゃう" not in chain_text:
                    has_issue = True
                    issue_notes.append("MISSING: しまう/ちゃう not shown in chain")
            
            # Check for iru (progressive) visibility
            if "iru" in label.lower() and "progressive" in label.lower():
                if "いる" not in chain_text and "progressive" not in chain_text.lower():
                    has_issue = True
                    issue_notes.append("MISSING: いる (progressive) not shown in chain")
            
            # Check for iku visibility
            if "iku" in label.lower() and "forward" in label.lower():
                if "いく" not in chain_text and "going" not in chain_text.lower():
                    has_issue = True 
                    issue_notes.append("MISSING: いく (forward) not shown in chain")
            
            # Check for oku/とく visibility
            if "oku" in label.lower() or "toku" in label.lower():
                if "おく" not in chain_text and "とく" not in chain_text:
                    has_issue = True
                    issue_notes.append("MISSING: おく/とく not shown in chain")
            
            # Check for miru visibility
            if "miru" in label.lower():
                if "みる" not in chain_text and "try" not in chain_text.lower():
                    has_issue = True
                    issue_notes.append("MISSING: みる (try) not shown in chain")
            
            # Check for ageru/morau/kureru
            if "ageru" in label.lower():
                if "あげる" not in chain_text:
                    has_issue = True
                    issue_notes.append("MISSING: あげる (giving) not shown")
            if "morau" in label.lower():
                if "もらう" not in chain_text:
                    has_issue = True
                    issue_notes.append("MISSING: もらう (receiving) not shown")
            if "kureru" in label.lower():
                if "くれる" not in chain_text:
                    has_issue = True
                    issue_notes.append("MISSING: くれる (receiving) not shown")
            
            # Check for aru (resultative)
            if "aru" in label.lower() and "resultative" in label.lower():
                if "ある" not in chain_text:
                    has_issue = True
                    issue_notes.append("MISSING: ある (resultative) not shown")
            
            # Check for hoshii
            if "hoshii" in label.lower():
                if "ほしい" not in chain_text:
                    has_issue = True
                    issue_notes.append("MISSING: ほしい (want) not shown")
        
        # Print result
        status = "BUG" if has_issue else "OK "
        print(f"[{status}] #{i:02d} {label}")
        print(f"       Input: {text}")
        print(f"       Expected: {expected}")
        if chain_lines:
            print(f"       Chain: {' | '.join(chain_lines)}")
        else:
            print(f"       Chain: (none)")
        if has_issue:
            for note in issue_notes:
                print(f"       >>> {note}")
        print()
        
        if has_issue:
            issues.append({
                "num": i,
                "text": text,
                "label": label,
                "expected": expected,
                "chain": chain_lines,
                "notes": issue_notes,
            })
    
    # Summary
    print("=" * 80)
    print(f"SUMMARY: {len(issues)} issues found out of {len(test_cases)} tests")
    print("=" * 80)
    
    if issues:
        print("\nFailing patterns:")
        for iss in issues:
            print(f"  #{iss['num']:02d} [{iss['label']}]: {', '.join(iss['notes'])}")
    
    return issues


if __name__ == "__main__":
    main()
