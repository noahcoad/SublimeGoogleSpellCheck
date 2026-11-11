# Live tests against Google's suggest endpoint -- needs a network connection.
#   python3 tests/test_correct.py
# Stubs the sublime modules so the plugin imports outside the editor.

import os, sys, time, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_sublime = types.ModuleType('sublime')
STATUS = []
_sublime.status_message = lambda m: STATUS.append(m)
TIMEOUTS = []		# queued, not run -- so tests can prove what's deferred to the next tick
_sublime.set_timeout = lambda f, t=0: TIMEOUTS.append(f)
class _Region:
	def __init__(self, a, b=None): self.a, self.b = a, b
_sublime.Region = _Region
_sublime.DRAW_NO_FILL, _sublime.DRAW_NO_OUTLINE, _sublime.DRAW_SQUIGGLY_UNDERLINE = 32, 256, 2048
sys.modules['sublime'] = _sublime

_plugin = types.ModuleType('sublime_plugin')
class _TextCommand:
	def __init__(self, *a): pass
_plugin.TextCommand = _TextCommand
sys.modules['sublime_plugin'] = _plugin

import GoogleSpellCheck as gsc

THROTTLE = 0.8		# the suggest endpoint returns 500s under rapid-fire use

# misspellings -> the correction we expect, or None for "any correction will do"
MISSPELLED = [
	('avalible', 'available'),
	('maitenence', 'maintenance'),
	('recieve', 'receive'),
	('seperate', 'separate'),
	('definately', 'definitely'),
	('occurance', 'occurrence'),
	('tommorrow', 'tomorrow'),
	('wierd', 'weird'),
	('accomodate', 'accommodate'),
	('concious', 'conscious'),
	('goverment', 'government'),
	('embarass', 'embarrass'),
	('flikr', 'flickr'),
	('craigslsit', 'craigslist'),
	('kubernets', 'kubernetes'),
	('jon sculzi', 'john scalzi'),			# names, via phrase context
	('pyton scrpit', 'python script'),
	('sublme text', 'sublime text'),
	('battery terminalss', 'battery terminals'),	# doubled trailing letter
	# google only offers extensions for the whole phrase, so this needs the
	# per-word pass; "additionassl" corrects fine on its own
	('additionassl microcontrollers', 'additional microcontrollers'),
	('recieve the pakcage', 'receive the package'),	# two bad words in one phrase
	# words run together: google returns MORE words than were typed, which the word-count
	# rule used to reject outright
	('anotherone', 'another one'),
	('alot of people', 'a lot of people'),
	# both at once -- and "dustr" alone is uncorrectable (google offers only brand names),
	# so only the phrase-level pass can fix it
	('anotherone bites the dustr', 'another one bites the dust'),
	# context decides: the same typo resolves differently, and alone it resolves to nothing
	('feather dustr', 'feather duster'),
	('clean the dustr', 'clean the dust'),
	# two typos in one phrase, where google's phrase suggestion fixes one and appends a
	# word ("...leadership style"). That must be refused as an extension so the per-word
	# pass runs and catches both -- check_word_highlights() has the unit case.
	('respcting a boss vs entitled leadersip', 'respecting a boss vs entitled leadership'),
]

# correctly spelled -- must be left completely alone
CORRECT = [
	'definitely',
	'receive',				# google suggests "received"; must not be applied
	'maintenance',
	'available',
	'separate',
	'tomorrow',
	'weird',
	'asynchronous',
	'kubernetes',
	'python',
	'avocado',
	'the quick brown fox',	# must not be extended to "...jumps over the lazy dog"
	'hello world',
	'battery terminals',
	'John Scalzi',
	'Sublime Text',
	'git rebase',
	'spell check',			# must not be joined into "spellcheck"
	'package control',		# ditto "packagecontrol"
	# the per-word pass must not "fix" words that are already right
	'additional microcontrollers',
	'the microcontroller reads the sensor',
	'sublime text package control',
	'wire the terminals to the battery',
]

# (input, expected) pairs that don't need the network
OFFLINE = [
	('', None),
	('   ', None),
	('123', None),
	('!!!', None),
	('x' * 500, None),
]


class _FakeView:
	"""Just enough view for the highlight command's _done -- records what it touched."""
	def __init__(self, text=''): self.marked, self.regions, self.replaced, self.text = None, {}, [], text
	def substr(self, r): return self.text[r.a:r.b]
	def erase_status(self, key): pass
	def add_regions(self, key, regions, *a, **kw): self.marked = (key, regions, a, kw)
	def erase_regions(self, key): self.regions.pop(key, None)
	def get_regions(self, key): return self.regions.get(key, [])
	def replace(self, *a): self.replaced.append(a)
	def run_command(self, *a, **kw): self.replaced.append(a)
	def sel(self):
		if not hasattr(self, 'selection'): self.selection = _FakeSel()
		return self.selection


class _FakeSel:
	def __init__(self): self.regions, self.cleared = [], False
	def clear(self): self.regions, self.cleared = [], True
	def add_all(self, regions): self.regions.extend(regions)


def check_highlight():
	"""Offline: highlighting marks regions and never edits the buffer."""
	fails = []
	cmd = gsc.GoogleSpellCheckHighlightCommand(None)
	cmd.view = _FakeView()
	cmd._done([{'region': [0, 8], 'text': 'available'}], 0, 1)
	if cmd.view.replaced:
		fails.append('highlight modified the buffer: %r' % (cmd.view.replaced,))
	if not cmd.view.marked or cmd.view.marked[0] != gsc.HIGHLIGHT_KEY:
		fails.append('highlight did not add regions under %r' % gsc.HIGHLIGHT_KEY)
	elif 'available' not in cmd.view.marked[2][3][0]:
		fails.append('highlight annotation missing the suggestion: %r' % (cmd.view.marked[2][3],))
	# both commands share the one _regions implementation
	if gsc.GoogleSpellCheckCommand._regions is not gsc.GoogleSpellCheckHighlightCommand._regions:
		fails.append('_regions is no longer shared between the two commands')
	return fails


def check_word_highlights():
	"""Offline: only the misspelled words get marked, not the whole selection."""
	fails = []
	# pure diffing, no network
	line = 'respecting a boss vs entitled leadersip'
	got = gsc._word_diffs(line, 'respecting a boss vs entitled leadership')
	if got != [(30, 39, 'leadership')]:
		fails.append('one bad word in a phrase marked %r, wanted [(30, 39, %r)]' % (got, 'leadership'))

	# punctuation stays outside the region, and off the annotation
	got = gsc._word_diffs('are avalible tommorow.', 'are available tomorrow.')
	if got != [(4, 12, 'available'), (13, 21, 'tomorrow')]:
		fails.append('punctuation not trimmed: %r' % (got,))

	# a word google split is ONE correction, and the typo next to it is a separate one --
	# the alignment must not collapse the whole phrase into a single lump
	got = gsc._word_diffs('anotherone bites the dustr', 'another one bites the dust')
	if got != [(0, 10, 'another one'), (21, 26, 'dust')]:
		fails.append('word split not aligned separately: %r' % (got,))

	# a pure addition has nothing of the source to mark, so the caller falls back
	if gsc._word_diffs('one two', 'one two three') != []:
		fails.append('_word_diffs marked something for an appended word')

	# and the command marks the word, not the region it was found in
	cmd = gsc.GoogleSpellCheckHighlightCommand(None)
	cmd.view = _FakeView(line)
	cmd._done([{'region': [0, len(line)], 'text': 'respecting a boss vs entitled leadership'}], 0, 1)
	marked = cmd.view.marked[1] if cmd.view.marked else []
	if [(r.a, r.b) for r in marked] != [(30, 39)]:
		fails.append('highlight marked %r, wanted just [(30, 39)]' % ([(r.a, r.b) for r in marked],))

	# the status bar lists the corrections, not the whole corrected text
	two = 'respcting a boss vs entitled leadersip'
	cmd = gsc.GoogleSpellCheckHighlightCommand(None)
	cmd.view = _FakeView(two)
	cmd._done([{'region': [0, len(two)], 'text': 'respecting a boss vs entitled leadership'}], 0, 1)
	if 'respecting, leadership (nothing changed)' not in STATUS[-1]:
		fails.append('status did not list the corrections: %r' % STATUS[-1])
	if gsc._summary(['a', 'b', 'c'], limit=2) != 'a, b +1 more':
		fails.append('summary cap wrong: %r' % gsc._summary(['a', 'b', 'c'], limit=2))

	# a split correction is listed as its own word, not as the whole corrected line
	run = 'anotherone bites the dustr'
	cmd = gsc.GoogleSpellCheckHighlightCommand(None)
	cmd.view = _FakeView(run)
	cmd._done([{'region': [0, len(run)], 'text': 'another one bites the dust'}], 0, 1)
	if [(r.a, r.b) for r in cmd.view.marked[1]] != [(0, 10), (21, 26)]:
		fails.append('split not marked as two spots: %r' % ([(r.a, r.b) for r in cmd.view.marked[1]],))
	if 'another one, dust' not in STATUS[-1]:
		fails.append('status lumped the split correction: %r' % STATUS[-1])

	# an appended word is an extension, even when a real typo is fixed alongside it
	if gsc._plausible('respcting a boss vs entitled leadersip',
					  'respcting a boss vs entitled leadership style'):
		fails.append('_plausible accepted a suggestion with an appended word')
	return fails


def check_fix_highlight():
	"""Offline: Fix and Highlight both replaces and marks, at the POST-fix offsets."""
	fails = []
	run = 'anotherone bites the dustr'
	fix = 'another one bites the dust'
	# 'another one' is 0..11 and 'dust' 22..26 once the text is a character longer
	got = [(r.a, r.b) for r, _ in gsc._fixed_spots(_FakeView(run), [{'region': [0, len(run)], 'text': fix}])]
	if got != [(0, 11), (22, 26)]:
		fails.append('post-fix spots %r, wanted [(0, 11), (22, 26)]' % (got,))

	cmd = gsc.GoogleSpellCheckFixHighlightCommand(None)
	cmd.view = _FakeView(run)
	del TIMEOUTS[:]
	cmd._done([{'region': [0, len(run)], 'text': fix}], 0, 1)
	if not cmd.view.replaced or cmd.view.replaced[0][0] != 'google_spell_check_replace':
		fails.append('fix+highlight did not apply the fix: %r' % (cmd.view.replaced,))
	# marking MUST wait for the next tick -- in the same one sublime maps the regions
	# through the replacement and shifts them all right by the length of the new text
	if cmd.view.marked:
		fails.append('fix+highlight marked in the same tick as the edit')
	if not TIMEOUTS:
		fails.append('fix+highlight did not defer the marking')
	for f in TIMEOUTS: f()
	if not cmd.view.marked or [(r.a, r.b) for r in cmd.view.marked[1]] != [(0, 11), (22, 26)]:
		fails.append('fix+highlight marked %r' % (cmd.view.marked and [(r.a, r.b) for r in cmd.view.marked[1]],))
	if 'fixed another one, dust' not in STATUS[-1]:
		fails.append('fix+highlight status wrong: %r' % STATUS[-1])

	return fails


def check_selection():
	"""Offline: Fix replaces back to front and leaves the selection completely alone."""
	fails = []
	cmd = gsc.GoogleSpellCheckReplaceCommand(None)
	cmd.view = _FakeView()
	# 'Avalible' -> 'Available' at 0, and ' tommorow ' -> ' tomorrow ' at 20
	cmd.run(None, [{'region': [0, 8], 'text': 'Available'},
				   {'region': [20, 30], 'text': ' tomorrow '}])

	if [a[1].a for a in cmd.view.replaced] != [20, 0]:
		fails.append('replacements not applied back to front: %r' % ([a[1].a for a in cmd.view.replaced],))
	# Fix's whole contract is that it fixes the spelling and touches nothing else
	if cmd.view.sel().cleared or cmd.view.sel().regions:
		fails.append('Fix moved the selection: cleared=%r regions=%r'
					 % (cmd.view.sel().cleared, cmd.view.sel().regions))

	cmd = gsc.GoogleSpellCheckCommand(None)
	cmd.view = _FakeView('avalible')
	cmd._done([{'region': [0, 8], 'text': 'available'}], 0, 1)
	if cmd.view.marked:
		fails.append('Fix added highlights: %r' % (cmd.view.marked,))
	if 'available' not in STATUS[-1]:
		fails.append('Fix did not name the correction: %r' % STATUS[-1])
	return fails


def check_flagged():
	"""Offline: a typo google flags only inside a completion is still corrected (issue #32)."""
	fails = []
	row = lambda a, b, rest='': ['<b>x</b>', 0, [], {'za': '<sc>%s</sc>%s' % (a, rest), 'zb': '<se>%s</se>%s' % (b, rest)}]
	# google's actual answer for "recieve", 2026-11-09: no bare "receive" row at all
	rows = [row('receiver', 'reciever'), row('received', 'recieved'), row('receives', 'recieves'),
			row('received', 'recieved', ' synonym'), row('receive', 'recieve', ' in spanish')]
	real = gsc._fetch
	gsc._fetch = lambda text: ['recieve', rows]
	try:
		for text, want in [('recieve', 'receive'), ('Recieve', 'Receive')]:
			got = gsc.correct(text)
			if got != want: fails.append('flagged-in-completion %r -> %r, wanted %r' % (text, got, want))
	finally:
		gsc._fetch = real
	# google echoes "alot of people" verbatim, and flags it only inside a longer completion
	# that also fixes a later word -- the flag must still win over the echo
	rows = [['alot of people', 0, []], ['alot of people<b> synonym</b>', 0, []],
			['x', 0, [], {'za': '<sc>a lot</sc> of people <sc>don&#39;t</sc> like me',
						  'zb': '<se>alot</se> of people <se>dont</se> like me'}]]
	gsc._fetch = lambda text: ['alot of people', rows]
	try:
		got = gsc.correct('alot of people')
		if got != 'a lot of people': fails.append('flag behind an echo: %r, wanted %r' % (got, 'a lot of people'))
	finally:
		gsc._fetch = real

	f = gsc._flagged
	cases = [
		('recieve the', '<sc>receive</sc> the', '<se>recieve</se> the', 'receive the'),			# exact
		('recieve', '<sc>received</sc> spelling', '<se>recieved</se> spelling', None),			# another word
		('recieve the pakcage', '<sc>receive</sc> the <sc>package</sc> tracking',
		 '<se>recieve</se> the <se>pakcage</se> tracking', 'receive the package'),			# two swaps, suffix dropped
		('alot of', '<sc>a lot</sc> of people', '<se>alot</se> of people', 'a lot of'),		# ends inside a plain run
		('alot of peop', '<sc>a lot</sc> of people', '<se>alot</se> of people', None),			# ends mid-word
		('the pakc', 'the <sc>package</sc>', 'the <se>pakcage</se>', None),					# flagged word straddles the end
		('the pakcage', 'a <sc>package</sc>', 'the <se>pakcage</se>', None),					# untagged text disagrees
	]
	for low, za, zb, want in cases:
		got = f(low, za, zb)
		if got != want: fails.append('_flagged(%r, %r) -> %r, wanted %r' % (low, zb, got, want))
	return fails


def main():
	fails = check_highlight() + check_word_highlights() + check_selection() + check_fix_highlight() + check_flagged()

	for text, expected in OFFLINE:
		got = gsc.correct(text)
		if got is not None:
			fails.append('offline %r -> %r, wanted None' % (text[:20], got))

	print('checking %d misspellings' % len(MISSPELLED))
	for text, expected in MISSPELLED:
		got = gsc.correct(text)
		time.sleep(THROTTLE)
		ok = got is not None and (expected is None or got.lower() == expected.lower())
		print('  %s %-20r -> %r' % ('ok  ' if ok else 'FAIL', text, got))
		if not ok:
			fails.append('%r -> %r, wanted %r' % (text, got, expected))

	print('checking %d correctly spelled' % len(CORRECT))
	for text in CORRECT:
		got = gsc.correct(text)
		time.sleep(THROTTLE)
		ok = got is None
		print('  %s %-20r -> %r' % ('ok  ' if ok else 'FAIL', text, got))
		if not ok:
			fails.append('%r changed to %r, wanted no change' % (text, got))

	# capitalization is carried over from what was typed
	for text, expected in [('Avalible', 'Available'), ('AVALIBLE', 'AVAILABLE')]:
		got = gsc.correct(text)
		time.sleep(THROTTLE)
		if got != expected:
			fails.append('case %r -> %r, wanted %r' % (text, got, expected))

	# +3 highlight, +4 selection, +9 word-highlight, +5 fix-and-highlight, +10 flagged
	total = len(OFFLINE) + len(MISSPELLED) + len(CORRECT) + 2 + 3 + 4 + 9 + 5 + 10
	if fails:
		print('\n%d of %d failed:' % (len(fails), total))
		for f in fails: print('  ' + f)
		return 1
	print('\nall %d passed' % total)
	return 0


if __name__ == '__main__':
	sys.exit(main())
