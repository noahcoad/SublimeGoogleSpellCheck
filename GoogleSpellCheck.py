# Replaces the word under the cursor or selection with Google's recommended spelling.
# Silent: if Google has no clear respelling, the text is left alone.
# The Highlight Only command runs the same lookups but marks them instead of editing.
# Hosted at https://github.com/noahcoad/SublimeGoogleSpellCheck

import sublime, sublime_plugin
import urllib.request, urllib.parse, difflib, json, re, html, threading, time

SUGGEST_URL = 'https://suggestqueries.google.com/complete/search'
# psy-ab is the only client that returns explicit spell-correction metadata:
# za = "<sc>corrected</sc>", zb = "<se>what you typed</se>"
CLIENT = 'psy-ab'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36'
TIMEOUT = 8
MAX_CHARS = 200
RETRIES = 3			# the endpoint 500s when hit rapidly, e.g. many selections at once
AGREE = object()	# sentinel: google returned the text unchanged, so leave it alone


def _detag(s):
	return html.unescape(re.sub(r'<.*?>', '', s or '')).strip()


def _fetch(text):
	url = '%s?client=%s&hl=en&gl=us&q=%s' % (SUGGEST_URL, CLIENT, urllib.parse.quote(text))
	for attempt in range(RETRIES):
		try:
			req = urllib.request.Request(url, headers={'User-Agent': UA})
			with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
				return json.loads(resp.read().decode('utf-8', 'replace'))
		except Exception:
			if attempt == RETRIES - 1: raise
			time.sleep(0.6 * (attempt + 1))


def _lev(a, b):
	prev = list(range(len(b) + 1))
	for i, ca in enumerate(a, 1):
		cur = [i]
		for j, cb in enumerate(b, 1):
			cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
		prev = cur
	return prev[-1]


def _plausible(src, cand):
	# a respelling keeps the same word count and stays close per word;
	# anything else is google extending the phrase, not correcting it
	sw, cw = src.split(), cand.split()
	# google extending what you typed is a completion, not a correction
	if cand.startswith(src): return False
	# you typing extra trailing characters IS a correction ("terminalss" -> "terminals"),
	# but only for a short tail, so a truncated phrase isn't mistaken for a fix
	if src.startswith(cand):
		tail = src[len(cand):]
		if len(tail) > 2 or ' ' in tail: return False
	if len(sw) != len(cw):
		# google re-spaced things ("anotherone" -> "another one"), which is a real fix, so
		# compare with the whitespace removed rather than word by word
		if len(cw) < len(sw): return False		# joining words is rarely a spelling fix
		ss, cs = re.sub(r'\s+', '', src), re.sub(r'\s+', '', cand)
		if cs == ss: return True				# purely a word split
		if cs.startswith(ss): return False		# still just an extension
		# re-spacing changes no letters and a typo fix changes very few, but appending a
		# whole word changes many -- and that's an extension however the words line up
		if abs(len(cs) - len(ss)) > 2: return False
		return _lev(ss, cs) <= max(2, len(ss) // 4)
	if _lev(src, cand) > max(2, len(src) // 4): return False
	for a, b in zip(sw, cw):
		if a == b: continue
		if _lev(a, b) > max(2, len(a) // 3): return False
		if a[0] != b[0]: return False
	return True


def _match_case(src, fix):
	if src.isupper(): return fix.upper()
	if src.istitle(): return fix.title()
	if src[:1].isupper(): return fix[:1].upper() + fix[1:]
	return fix


def correct(text):
	"""Google's respelling of text, or None if google has no clear correction."""
	src = text.strip()
	if not src or len(src) > MAX_CHARS: return None
	if not re.search(r'[a-zA-Z]', src): return None

	fix = _correct_phrase(src)
	if fix is AGREE: return None		# google echoed it back, spelling is fine
	if fix: return fix
	# google had no correction for the phrase as a whole, so try word by word:
	# it corrects "additionassl" alone but only offers extensions for
	# "additionassl microcontrollers"
	return _correct_words(src)


def _flagged(low, za, zb):
	"""The correction of low from one flagged row, or None if the row isn't about low.
	zb wraps each typo in <se>, za wraps its fix in <sc>, in the same order. google often
	flags your text only inside a longer completion -- "<se>alot</se> of people <se>dont</se>
	like me" -- so pair the tags up and keep only the swaps that fall within what you typed."""
	pa, pb = re.split(r'<sc>(.*?)</sc>', za), re.split(r'<se>(.*?)</se>', zb)
	if len(pa) != len(pb): return None
	plain = lambda t: html.unescape(re.sub(r'<.*?>', '', t))
	typed, out = '', ''
	for i, (a, b) in enumerate(zip(map(plain, pa), map(plain, pb))):
		if i % 2 == 0:
			if a.lower() != b.lower(): return None		# untagged text must agree, or the pairing is off
			n = len(low) - len(typed.lstrip())			# how much of this plain run is still yours
			if n <= len(b):
				if not (typed + b).lstrip().lower().startswith(low): return None
				if n < len(b) and not b[n].isspace(): return None	# ends mid-word
				return (out + a[:n]).strip()
		else:
			if len((typed + b).lstrip()) > len(low): return None	# a flagged word straddles the end
		typed, out = typed + b, out + a
	return None


def _correct_phrase(src):
	"""A respelling of the whole phrase, AGREE if google echoed it back, else None."""
	data = _fetch(src)
	rows = data[1] if len(data) > 1 else []
	low = src.lower()
	nwords = len(low.split())

	# google explicitly flagged a misspelling
	for row in rows:
		meta = row[3] if len(row) > 3 and isinstance(row[3], dict) else {}
		za, zb = meta.get('za'), meta.get('zb')
		if not (za and zb): continue
		cand = _flagged(low, za, zb)
		if not cand: continue
		if cand.lower() == low: continue
		# same word count, or a re-spacing google flagged outright
		if len(cand.split()) == nwords or _plausible(low, cand.lower()):
			return _match_case(src, cand)

	# no explicit flag: accept a top suggestion only if it reads as a respelling
	for row in rows[:5]:
		cand = _detag(row[0])
		cl = cand.lower()
		if cl == low: return AGREE		# google offered it back verbatim
		if _plausible(low, cl): return _match_case(src, cand)

	return None


def _correct_words(src):
	"""Check each word on its own; returns None unless some word was corrected."""
	words = re.split(r'(\s+)', src)					# keeps the separators, so spacing survives
	if len(src.split()) < 2: return None

	out = []
	changed = False
	for w in words:
		if not w.strip():
			out.append(w)
			continue
		lead = re.match(r'^\W*', w).group(0)			# keep punctuation attached to the word
		trail = re.search(r'\W*$', w).group(0)
		core = w[len(lead):len(w) - len(trail)] if trail else w[len(lead):]
		if len(core) < 4 or not core.isalpha():
			out.append(w)
			continue
		fix = _correct_phrase(core)
		if fix and fix is not AGREE:
			out.append(lead + fix + trail)
			changed = True
		else:
			out.append(w)

	return ''.join(out) if changed else None


HIGHLIGHT_KEY = 'google_spell_check_highlight'


def _inner(s, a, b):
	"""a,b narrowed past any punctuation stuck to the ends -- that isn't the misspelling."""
	t = s[a:b]
	lead = len(re.match(r'^\W*', t).group(0))
	trail = len(re.search(r'\W*$', t).group(0))
	return (a + lead, b - trail) if a + lead < b - trail else (a, b)


def _align(src, fix):
	"""(src span, fix span, replacement) per changed chunk. Aligned rather than zipped, so a
	word google split ("anotherone" -> "another one") stays one chunk while two neighbouring
	typos stay two. Empty when nothing of src changed."""
	sp = [m.span() for m in re.finditer(r'\S+', src)]
	fp = [m.span() for m in re.finditer(r'\S+', fix)]
	st, ft = [src[a:b] for a, b in sp], [fix[a:b] for a, b in fp]
	out = []
	for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=st, b=ft).get_opcodes():
		if tag == 'equal' or i1 == i2 or j1 == j2: continue		# nothing of src to mark
		if i2 - i1 == j2 - j1:									# word for word
			groups = [(i, i + 1, j, j + 1) for i, j in zip(range(i1, i2), range(j1, j2))]
		else:
			groups = [(i1, i2, j1, j2)]							# a split spans the whole block
		for a1, a2, b1, b2 in groups:
			sa, sb = _inner(src, sp[a1][0], sp[a2 - 1][1])
			fa, fb = _inner(fix, fp[b1][0], fp[b2 - 1][1])
			out.append(((sa, sb), (fa, fb), fix[fa:fb]))
	return out


def _word_diffs(src, fix):
	"""(start, end, replacement) per changed word, offsets into src."""
	return [(a, b, word) for (a, b), _, word in _align(src, fix)]


def _fix_spots(view, fixes):
	"""(Region, corrected word) for every changed word, in document order."""
	spots = []
	for f in sorted(fixes, key=lambda x: x['region'][0]):
		a, b = f['region']
		src = view.substr(sublime.Region(a, b))
		for s, e, word in _word_diffs(src, f['text']) or [(0, len(src), f['text'])]:
			spots.append((sublime.Region(a + s, a + e), word.strip()))
	return spots


def _fixed_spots(view, fixes):
	"""The same, but in the coordinates the buffer will have AFTER the fixes are applied --
	so the corrections can be marked where they land. Call before replacing."""
	spots, delta = [], 0
	for f in sorted(fixes, key=lambda x: x['region'][0]):
		a, b = f['region']
		src, fix = view.substr(sublime.Region(a, b)), f['text']
		for _, (s, e), word in _align(src, fix) or [(None, (0, len(fix)), fix)]:
			spots.append((sublime.Region(a + delta + s, a + delta + e), word.strip()))
		delta += len(fix) - (b - a)
	return spots


def _summary(words, limit=8):
	"""The corrections as a list, since the status bar has no room for whole paragraphs."""
	if len(words) <= limit: return ', '.join(words)
	return '%s +%d more' % (', '.join(words[:limit]), len(words) - limit)


class _CheckCommand(sublime_plugin.TextCommand):
	"""Shared lookup plumbing: what to check, on a thread, then hand off to _done."""

	def is_visible(self):
		# keeps the context menu entry conditional -- it only shows when there's
		# actually a word or selection to check
		return bool(self._regions())

	def _regions(self):
		regions = []
		for sel in self.view.sel():
			r = sel if not sel.empty() else self.view.word(sel)
			if not self.view.substr(r).strip(): continue
			regions.append((r.a, r.b))
		return regions

	def run(self, edit):
		regions = self._regions()
		if not regions:
			sublime.status_message('Google Spell Check: nothing to check')
			return

		self.view.set_status('google_spell_check', 'Google Spell Check: checking...')
		threading.Thread(target=self._work, args=(regions,), daemon=True).start()

	def _work(self, regions):
		fixes = []
		errors = 0
		for a, b in regions:
			text = self.view.substr(sublime.Region(a, b))
			try:
				fix = correct(text)
			except Exception:
				errors += 1
				continue
			if not fix: continue
			lead = text[:len(text) - len(text.lstrip())]		# keep any selected whitespace
			trail = text[len(text.rstrip()):]
			fix = lead + fix + trail
			if fix != text:
				fixes.append({'region': [a, b], 'text': fix})
		sublime.set_timeout(lambda: self._done(fixes, errors, len(regions)), 0)

	def _ready(self, fixes, errors):
		"""Reports the outcomes there's nothing to act on; True when there are fixes."""
		self.view.erase_status('google_spell_check')
		if errors:
			sublime.status_message('Google Spell Check: could not reach Google (check your connection)')
			if not fixes: return False
		if not fixes:
			sublime.status_message('Google Spell Check: spelling looks good')
			return False
		return True

	def _mark(self, spots):
		"""Squiggle each misspelled word and annotate it with the correction."""
		regions, words = [s[0] for s in spots], [s[1] for s in spots]
		# annotations are minihtml, so the suggestions have to be escaped
		notes = ['<b>%s</b>' % html.escape(w) for w in words]
		self.view.add_regions(
			HIGHLIGHT_KEY, regions, 'region.orangish', 'dot',
			sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_SQUIGGLY_UNDERLINE,
			notes, '#f90',
			on_close=lambda: self.view.erase_regions(HIGHLIGHT_KEY))
		return words


class GoogleSpellCheckCommand(_CheckCommand):
	def _done(self, fixes, errors, total):
		if not self._ready(fixes, errors): return
		words = [w for _, w in _fix_spots(self.view, fixes)]		# before the buffer changes
		self.view.run_command('google_spell_check_replace', {'fixes': fixes})
		sublime.status_message('Google Spell Check: %s' % _summary(words))


class GoogleSpellCheckHighlightCommand(_CheckCommand):
	"""Same lookups, but only marks what would change -- the buffer is never touched."""

	def _done(self, fixes, errors, total):
		self.view.erase_regions(HIGHLIGHT_KEY)
		if not self._ready(fixes, errors): return
		# mark the individual misspelled words, not the whole selection
		words = self._mark(_fix_spots(self.view, fixes))
		sublime.status_message('Google Spell Check: %s (nothing changed)' % _summary(words))


class GoogleSpellCheckFixHighlightCommand(_CheckCommand):
	"""Fixes the spelling AND leaves the corrections marked, so you can see what it did."""

	def _done(self, fixes, errors, total):
		self.view.erase_regions(HIGHLIGHT_KEY)
		if not self._ready(fixes, errors): return
		spots = _fixed_spots(self.view, fixes)					# where they'll land, before replacing
		self.view.run_command('google_spell_check_replace', {'fixes': fixes})
		words = [w for _, w in spots]
		# mark on the next tick: regions added in the same one are still mapped through the
		# replacement, which shifts every one of them right by the length of the new text
		sublime.set_timeout(lambda: self._mark(spots), 0)
		sublime.status_message('Google Spell Check: fixed %s' % _summary(words))


class GoogleSpellCheckClearHighlightsCommand(sublime_plugin.TextCommand):
	def is_visible(self):
		return bool(self.view.get_regions(HIGHLIGHT_KEY))

	def run(self, edit):
		self.view.erase_regions(HIGHLIGHT_KEY)
		sublime.status_message('Google Spell Check: highlights cleared')


class GoogleSpellCheckReplaceCommand(sublime_plugin.TextCommand):
	def run(self, edit, fixes):
		# back to front so earlier replacements don't shift later regions. the selection is
		# deliberately left alone -- sublime carries it over the replacement on its own, and
		# moving it would be a surprise from a command whose job is to fix spelling
		for f in sorted(fixes, key=lambda x: x['region'][0], reverse=True):
			self.view.replace(edit, sublime.Region(*f['region']), f['text'])
