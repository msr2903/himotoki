# 🧶 Himotoki v0.1.1 - CLI Improvements

A quality-of-life update focused on improving the command-line experience.

---

## ⚠️ Breaking Changes

The CLI output flags have been redesigned for better usability:

| Before | After | Description |
|--------|-------|-------------|
| `himotoki "text"` | `himotoki -r "text"` | Simple romanization |
| `himotoki -i "text"` | *removed* | — |
| `himotoki -f "text"` | `himotoki -j "text"` | JSON output |
| — | `himotoki "text"` | Dictionary info only (new default) |
| — | `himotoki -f "text"` | Full output (romanize + dict) |
| — | `himotoki -k "text"` | Kana with spaces |

---

## 🔧 New CLI Flags

```bash
# Default: Dictionary info only
himotoki "日本語"

# -r: Simple romanization
himotoki -r "日本語"
# → nihongo

# -f: Full output (romanization + dictionary info)
himotoki -f "日本語"

# -k: Kana reading with spaces
himotoki -k "日本語"
# → にほんご

# -j: JSON output
himotoki -j "日本語"
```

### Mutually Exclusive Flags

Output flags are now mutually exclusive. Using conflicting flags will show an error:

```bash
$ himotoki -r -f "日本語"
himotoki: error: argument -f/--full: not allowed with argument -r/--romanize
```

---

## ✨ Improvements

- **Better input validation**: Whitespace-only input is now properly rejected
- **Enhanced error messages**: Errors now include the output mode for easier debugging
- **Constants**: Added `VERSION` and `CONJUGATION_ROOT` constants for maintainability
- **Robust kana extraction**: New `get_kana()` helper handles edge cases

---

## 🧪 Testing

Added 34 comprehensive CLI tests covering:
- All output modes (-r, -f, -k, -j)
- Mutually exclusive flag validation
- Input validation (empty, whitespace)
- Error handling with mode context
- Constants and helper functions

---

## 📦 Installation

```bash
pip install --upgrade himotoki
```

---

**Full Changelog**: https://github.com/msr2903/himotoki/compare/v0.1.0...v0.1.1
