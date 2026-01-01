#!/usr/bin/env python3
"""
Himotoki vs Ichiran Evaluator

This script compares Himotoki's segmentation results with Ichiran's,
treating Ichiran as the ground truth. It measures similarity based on
sentence splitting (tokenization) and result formatting (metadata).
"""

import subprocess
import json
import sys
import os
import argparse
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

# Constants
ICHIRAN_CONTAINER = "ichiran-main-1"
ICHIRAN_TIMEOUT = 15
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SENTENCES_FILE = os.path.join(os.path.dirname(__file__), "sentences.json")

# Ensure project root is in path
sys.path.insert(0, PROJECT_ROOT)

@dataclass
class Token:
    text: str
    kana: str = ""
    pos: List[str] = field(default_factory=list)
    source: str = "" # "ichiran" or "himotoki"

    def __eq__(self, other):
        if not isinstance(other, Token):
            return False
        # Main point is text splitting
        return self.text == other.text

    def formatting_match(self, other):
        """Check if formatting (metadata) matches."""
        if not isinstance(other, Token):
            return False
        # Normalize kana for comparison
        k1 = self.kana.replace(" ", "")
        k2 = other.kana.replace(" ", "")
        return self.text == other.text and k1 == k2

def get_ichiran_tokens(text: str) -> List[Token]:
    """Get detailed Ichiran tokens."""
    try:
        result = subprocess.run(
            ["docker", "exec", ICHIRAN_CONTAINER, "ichiran-cli", "-f", text],
            capture_output=True, text=True, timeout=ICHIRAN_TIMEOUT
        )
        if result.returncode != 0:
            return []
        
        data = json.loads(result.stdout)
        if not data or not data[0] or not data[0][0]:
            return []
        
        best_interpretation = data[0][0]
        segments_data = best_interpretation[0]
        
        tokens = []
        for seg in segments_data:
            if len(seg) < 2: continue
            info = seg[1]
            if "compound" in info:
                # Ichiran compounds are lists of components
                comp_texts = info["compound"]
                comp_infos = info.get("components", [])
                for i, t in enumerate(comp_texts):
                    c_info = comp_infos[i] if i < len(comp_infos) else {}
                    t_pos = []
                    for gloss in c_info.get("gloss", []):
                        if "pos" in gloss: t_pos.append(gloss["pos"])
                    tokens.append(Token(text=t, kana=c_info.get("kana", ""), pos=t_pos, source="ichiran"))
            else:
                # Regular word
                word_info = info
                if "alternative" in info and info["alternative"]:
                    word_info = info["alternative"][0]
                
                t_pos = []
                for gloss in word_info.get("gloss", []):
                    if "pos" in gloss: t_pos.append(gloss["pos"])
                
                tokens.append(Token(
                    text=word_info.get("text", ""),
                    kana=word_info.get("kana", ""),
                    pos=t_pos,
                    source="ichiran"
                ))
        return tokens
    except Exception:
        return []

def get_himotoki_tokens(text: str) -> List[Token]:
    """Get detailed Himotoki tokens."""
    try:
        from himotoki.dict import simple_segment, get_senses
        words = simple_segment(text)
        tokens = []
        for w in words:
            kana = w.kana
            if isinstance(kana, list):
                kana = kana[0] if kana else ""
            
            t_pos = []
            if w.seq:
                senses = get_senses(w.seq)
                if senses:
                    t_pos = senses[0].get("pos", [])
            
            tokens.append(Token(text=w.text, kana=kana, pos=t_pos, source="himotoki"))
        return tokens
    except Exception:
        return []

def format_split_diff(i_tokens: List[Token], h_tokens: List[Token]) -> str:
    """Generate a visual diff of splitting."""
    i_str = " | ".join([t.text for t in i_tokens])
    h_str = " | ".join([t.text for t in h_tokens])
    return f"Ichiran:  [{i_str}]\nHimotoki: [{h_str}]"

def run_evaluation(sentences_data: Dict[str, List[str]]):
    print("=" * 60)
    print("Himotoki vs Ichiran Evaluation: Splitting & Formatting")
    print("=" * 60)
    
    overall_total = 0
    overall_split_matches = 0
    overall_format_matches = 0
    category_results = {}
    
    for category, sentences in sentences_data.items():
        print(f"\nCategory: {category}")
        cat_split_matches = 0
        cat_format_matches = 0
        cat_results = []
        
        for sentence in sentences:
            i_tokens = get_ichiran_tokens(sentence)
            h_tokens = get_himotoki_tokens(sentence)
            
            # 1. Splitting match (text list is identical)
            split_match = ([t.text for t in i_tokens] == [t.text for t in h_tokens])
            
            # 2. Formatting match (metadata match for identical splits)
            format_match = False
            if split_match:
                format_match = all(t_i.formatting_match(t_h) for t_i, t_h in zip(i_tokens, h_tokens))
            
            if split_match: cat_split_matches += 1
            if format_match: cat_format_matches += 1
            
            status = "✓" if split_match else "✗"
            if split_match and not format_match: status = "~" # Splitting ok, formatting diff
            
            print(f"  {status} {sentence}")
            
            # Show splitting and formatting details
            print("    Ichiran:  ", end="")
            i_parts = []
            for t in i_tokens:
                i_parts.append(f"{t.text}({t.kana})")
            print(" | ".join(i_parts))
            
            print("    Himotoki: ", end="")
            h_parts = []
            for t in h_tokens:
                h_parts.append(f"{t.text}({t.kana})")
            print(" | ".join(h_parts))
            
            if not split_match:
                print("    [Splitting Mismatch]")
            elif not format_match:
                print("    [Formatting/Metadata Mismatch]")
            print()
            
            cat_results.append({
                "sentence": sentence,
                "split_match": split_match,
                "format_match": format_match,
                "ichiran": i_tokens,
                "himotoki": h_tokens
            })
        
        split_sim = (cat_split_matches / len(sentences)) * 100 if sentences else 0
        format_sim = (cat_format_matches / len(sentences)) * 100 if sentences else 0
        print(f"  Splitting Similarity:  {split_sim:.1f}%")
        print(f"  Formatting Similarity: {format_sim:.1f}%")
        
        category_results[category] = {
            "split_similarity": split_sim,
            "format_similarity": format_sim,
            "results": cat_results
        }
        
        overall_total += len(sentences)
        overall_split_matches += cat_split_matches
        overall_format_matches += cat_format_matches
    
    overall_split_sim = (overall_split_matches / overall_total) * 100 if overall_total else 0
    overall_format_sim = (overall_format_matches / overall_total) * 100 if overall_total else 0
    
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"Total Sentences:         {overall_total}")
    print(f"Splitting Similarity:    {overall_split_sim:.2f}%")
    print(f"Formatting Similarity:   {overall_format_sim:.2f}%")
    print("=" * 60)
    
    return {
        "overall_split_similarity": overall_split_sim,
        "overall_format_similarity": overall_format_sim,
        "total_sentences": overall_total,
        "categories": category_results
    }

def generate_report(results: Dict[str, Any]):
    report_path = os.path.join(os.path.dirname(__file__), "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Detailed Evaluation Report: Himotoki vs Ichiran\n\n")
        f.write(f"- **Splitting Similarity:** {results['overall_split_similarity']:.2f}%\n")
        f.write(f"- **Formatting Similarity:** {results['overall_format_similarity']:.2f}%\n\n")
        
        f.write("## Category Performance\n\n")
        f.write("| Category | Splitting | Formatting |\n")
        f.write("| :--- | :--- | :--- |\n")
        for cat, data in results['categories'].items():
            f.write(f"| {cat} | {data['split_similarity']:.1f}% | {data['format_similarity']:.1f}% |\n")
        
        f.write("\n## Sentence Splitting Mismatches (Main Point)\n\n")
        for cat, data in results['categories'].items():
            mismatches = [r for r in data['results'] if not r['split_match']]
            if mismatches:
                f.write(f"### {cat}\n\n")
                for m in mismatches:
                    f.write(f"**Sentence:** {m['sentence']}\n")
                    f.write("```\n")
                    f.write(format_split_diff(m['ichiran'], m['himotoki']))
                    f.write("\n```\n\n")

        f.write("\n## Metadata/Formatting Mismatches\n\n")
        for cat, data in results['categories'].items():
            mismatches = [r for r in data['results'] if r['split_match'] and not r['format_match']]
            if mismatches:
                f.write(f"### {cat}\n\n")
                f.write("| Token | Ichiran Kana | Himotoki Kana |\n")
                f.write("| :--- | :--- | :--- |\n")
                for m in mismatches:
                    for t_i, t_h in zip(m['ichiran'], m['himotoki']):
                        if not t_i.formatting_match(t_h):
                            f.write(f"| {t_i.text} | {t_i.kana} | {t_h.kana} |\n")
                f.write("\n")
    
    print(f"\nReport generated at {report_path}")

def main():
    parser = argparse.ArgumentParser(description="Evaluate Himotoki splitting and formatting")
    parser.add_argument("--check", action="store_true", help="Check connectivity")
    parser.add_argument("--sentence", type=str, help="Evaluate single sentence")
    args = parser.parse_args()
    
    if args.check:
        print("Checking Ichiran...")
        tokens = get_ichiran_tokens("猫が食べる")
        for t in tokens: print(f"I: {t.text} ({t.kana}) {t.pos}")
        print("Checking Himotoki...")
        tokens = get_himotoki_tokens("猫が食べる")
        for t in tokens: print(f"H: {t.text} ({t.kana}) {t.pos}")
        return

    if args.sentence:
        i_tokens = get_ichiran_tokens(args.sentence)
        h_tokens = get_himotoki_tokens(args.sentence)
        print(f"Sentence: {args.sentence}")
        print(format_split_diff(i_tokens, h_tokens))
        return

    with open(SENTENCES_FILE, "r", encoding="utf-8") as f:
        sentences_data = json.load(f)
    results = run_evaluation(sentences_data)
    generate_report(results)

if __name__ == "__main__":
    main()
