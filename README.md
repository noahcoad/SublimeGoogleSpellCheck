# Google Spell Check
a Sublime Text package

Package Control: https://packagecontrol.io/packages/Google%20Spell%20Check

## Description
Use Google magic to fix spelling. Select some text (or just put the cursor on a word), run the command, and the text is silently replaced with Google's recommended spelling. If Google has no clear correction, **your text is left alone**.

Google has a far better spell checker than most tools:

1. **Frequency** — Google sees misspellings all day long, so it knows what you probably meant
1. **Names** — company names like `flikr` or `tumblr`, or scifi author `jon sculzi` → `john scalzi`; typical checkers look one word at a time and have no idea
1. **Unlimited dictionary** — `kubernetes`, `hackathons`, `craigslist`
1. **Context** — the whole phrase is considered, not each word alone
1. **It just works** — Sublime's built-in checker has no idea what to do with `avalible`, `finanicals`, `maitenence`

## The Commands
| Command | What it does |
|---|---|
| **Google Spell Check: Fix** | Replaces the misspellings, silently, and touches nothing else |
| **Google Spell Check: Fix and Highlight** | Replaces them *and* marks each one, so you can see what it changed |
| **Google Spell Check: Highlight Only** | Marks what it *would* change and touches nothing |
| **Google Spell Check: Clear Highlights** | Removes the marks |

## How to Use
1. Select some text, or put the cursor on a word
1. Run **Google Spell Check: Fix**
	* right-click context menu → Google Spell Check: Fix
	* Command Palette (`ctrl+shift+p` / `cmd+shift+p`) → Google Spell Check: Fix
	* or a key binding of your own — see below
1. The status bar shows progress, then the corrections it made

Multiple cursors/selections are all checked in one go. Capitalization is preserved (`Avalible` → `Available`, `AVALIBLE` → `AVAILABLE`).

**Fix changes nothing but the spelling** — your selection and any existing highlights are left as they were. To see what it changed, use **Fix and Highlight** instead: same edits, but each correction gets squiggled and annotated.

If nothing changes, Google thinks your spelling is fine. Select more words to give it context.

**Context matters, so select whole phrases.** `dustr` on its own corrects to nothing — Google only offers brand names for it. In context it resolves differently and correctly: `feather dustr` → `feather duster`, `clean the dustr` → `clean the dust`. Words run together are fixed too (`anotherone` → `another one`).

## Highlight Only (look before you leap)
**Google Spell Check: Highlight Only** does the same lookups but **never modifies the buffer**. Each misspelled **word** gets a squiggly underline, a gutter dot, and an inline annotation at the right edge showing the correction it *would* have made — only the bad words are marked, not everything you selected.

That's the one to use on anything that isn't prose. Run the plain command over code and Google will cheerfully "correct" identifiers like `const` or `EN`; Highlight Only shows you that first instead of rewriting the file.

1. Select some text (or the whole file with `ctrl+a` / `cmd+a`)
1. Run **Google Spell Check: Highlight Only** — right-click menu or Command Palette
1. Read the annotations, then either fix things yourself or run **Google Spell Check: Fix** on just the selections you agree with

Clear the marks with **Google Spell Check: Clear Highlights**, or click the `x` at the right edge of the annotations.

## Key Binding
No key binding is claimed by default, so nothing of yours gets clobbered. The suggested one lives in `Example.sublime-keymap`, which Sublime never loads — open it via **Preferences → Package Settings → Google Spell Check → Example Key Bindings** (or the Command Palette → *Preferences: Google Spell Check Example Key Bindings*) and copy this line to the right-hand User side:

```json
{ "keys": ["ctrl+alt+g"], "command": "google_spell_check" },
{ "keys": ["ctrl+alt+shift+g"], "command": "google_spell_check_fix_highlight" },
{ "keys": ["ctrl+alt+h"], "command": "google_spell_check_highlight" },
```

## How It Works
This uses Google's public autocomplete/suggest endpoint (`suggestqueries.google.com`), which returns explicit spell-correction metadata — Google marks *"you typed X, I think you meant Y"*. That flag is what makes silent replacement safe: without it, the plugin doesn't touch your text.

When Google doesn't flag anything, a suggestion is accepted only if it reads as a respelling — same word count, small per-word edit distance, same first letter. This is what stops Google from "correcting" `receive` into `received`, or `the quick brown fox` into `the quick brown fox jumps over the lazy dog`.

Some misspellings are invisible at phrase level: for `additionassl microcontrollers` Google only offers to extend the phrase, though `additionassl` alone corrects cleanly. So when the phrase as a whole yields no correction, each word is checked on its own (words under 4 characters are skipped, punctuation and spacing are preserved).

No API key required. It isn't an officially supported API, so Google changing their response format could break the plugin.

## Tests
`tests/test_correct.py` runs the correction logic against the live endpoint, stubbing the `sublime` modules so the plugin imports outside the editor:

```bash
py tests/test_correct.py
```

Needs a network connection. Covers misspellings that must be corrected, correctly spelled text that must be left untouched, case preservation, and offline input guards.

## Installation
* **Package Control** (recommended): `Package Control: Install Package` → **Google Spell Check**
* **Manual**: clone into your Sublime `Packages` folder

```bash
git clone https://github.com/noahcoad/SublimeGoogleSpellCheck.git "Google Spell Check"
```

Requires **Sublime Text 4** (build 4107+). The package ships a `.python-version` of `3.8`, so it runs in ST4's 3.8 plugin host — ST3's 3.3 host lacks `html.unescape`.

## Update Notices
* *2026-09-19* (**v2.2.1**), **Fix** is back to touching nothing but the spelling — v2.2.0 briefly had it move your selection onto the corrected words. If you want to see what changed, that's what **Fix and Highlight** is for.
* *2026-09-19* (**v2.2.0**), three new commands and a clearer naming: the original command is now **Google Spell Check: Fix** in the palette (the command name `google_spell_check` is unchanged, so existing key bindings keep working), joined by **Fix and Highlight**, **Highlight Only**, and **Clear Highlights**. See [The Commands](#the-commands) and [Highlight Only](#highlight-only-look-before-you-leap). Only the misspelled words are marked rather than the whole selection, the status bar lists the corrections, and words run together (`anotherone` → `another one`) are now fixed.
* *2026-09-08* (**v2.1.0**), Package Control housekeeping: added a `LICENSE`, started shipping `.python-version` (it was accidentally gitignored, which would have left an installed copy in the 3.3 plugin host), added the Preferences menu, and stopped claiming `ctrl+alt+g` by default — it now ships commented out for you to opt into. See [Key Binding](#key-binding).
* *2026-07-27* (**v2.0.0**), rewritten for Python 3 / ST4. The old version scraped the Google search results page for "Did you mean" — Google removed that markup, so it silently stopped working. Now uses the suggest endpoint's spell-correction metadata, falls back to per-word checking, checks all selections at once, preserves case and spacing, and reports connection failures instead of failing quietly. The `st2` and `st3` branches are retired; everything lives on `master`.
* *2013-10-14*, Sublime Text 3 version added.

## License
MIT — see [LICENSE](LICENSE).

## Finally
See also: [Open URL](https://packagecontrol.io/packages/Open%20URL) and [other](https://packagecontrol.io/browse/authors/noahcoad) Sublime packages.

Author: [@noahcoad](http://twitter.com/noahcoad) writes software for the heck of it and to make life just a little more efficient.
