# 🧩 lc — terminal LeetCode practice

Pick a problem, solve it in your own editor, run and submit it against LeetCode's
servers, and track your progress with spaced-repetition reviews, all from the terminal.

## Install

```bash
pip install -e .          # gives you the `lc` (and `leet`) command, usable from any folder
lc config                 # paste your LeetCode cookies (needed for run/submit)
```

To get your cookies: log in at leetcode.com → DevTools → Application → Cookies →
`leetcode.com` → copy `LEETCODE_SESSION` and `csrftoken`. LeetCode sessions expire
after a while; when they do, `lc` tells you to re-run `lc config`.

## Daily workflow

```bash
lc                        # dashboard (same as `lc dash`): NeetCode 150 with your progress
lc random                 # random *unsolved* problem from your default list
lc review                 # re-solve problems due for review (spaced repetition)
lc daily                  # today's LeetCode daily challenge
lc stats                  # progress by difficulty, topic and list
```

Every solve opens your editor, starts a timer, and then offers
`run / submit / edit / hints / quit`. Passing all sample tests offers to submit.

## Dashboard

`lc` (or `lc dash`, `lc dashboard`) opens a full-screen view of a list, which is
**NeetCode 150** by default (`lc dash --list questions` for another). It shows
your overall and per-difficulty progress, reviews due, your streak, and every
problem grouped by section, with solved/attempted marks, submit counts and
review dates. Problems that aren't cached yet are fetched in the background,
and their titles and difficulties fill in as they arrive.

| Key | Action |
|---|---|
| `Ctrl+N` / `↓` / `j`, `Ctrl+P` / `↑` / `k` | move |
| `PgDn` / `PgUp`, `g` / `G` | page, top / bottom |
| `Enter` | solve the selected problem (returns to the dashboard afterwards) |
| `o` | open it on leetcode.com |
| `f` | status filter: all → unsolved → solved → due for review |
| `d` | difficulty filter: any → Easy → Medium → Hard |
| `/` | search by title (`Enter` keeps it, `Esc` clears) |
| `r` | jump to a random unsolved problem in the current view |
| `q` | quit |

When output isn't a terminal, `lc dash` prints the same list as `lc list neetcode150`.

## Menus

Menus (the post-edit one, and the `lc review` picker) are keyboard-driven:

| Key | Action |
|---|---|
| `Ctrl+N` / `↓` / `j` | next |
| `Ctrl+P` / `↑` / `k` | previous |
| `Enter` | select |
| `r` `s` `e` `h` `q` | pick run / submit / edit / hints / quit directly |
| `1`–`9` | pick that option directly |
| `Esc` | cancel (quit) |

When input isn't a terminal (piped or scripted), menus fall back to a typed prompt.

## Commands

| Command | What it does |
|---|---|
| `lc` / `lc dash [--list NAME]` | Interactive dashboard (default list: neetcode150) |
| `lc random [--list NAME] [-d easy\|medium\|hard] [-t TOPIC] [--include-solved]` | Random problem; filters are repeatable (`-d medium -d hard`, `-t "dynamic"`) |
| `lc solve <slug\|url>` | Show → editor → run/submit |
| `lc daily` | Solve today's daily challenge |
| `lc review` | Pick from problems due for review |
| `lc show <slug\|url> [--hints] [--refresh]` | Just display a problem |
| `lc run <slug> [FILE] [--input "..."]` | Run examples + your `@tests` (doesn't count as a submission) |
| `lc submit <slug> [FILE]` | Real submission |
| `lc stats` | Solved counts, acceptance rate, streak, avg time, list progress, topics |
| `lc list [NAME]` | A list with ✓ solved / ◐ attempted marks and next review dates |
| `lc add <slug\|url> [--list NAME]` | Add a problem to a list (creates the list if needed) |
| `lc mark <slug>... [--unsolved]` | Record problems you solved elsewhere |
| `lc cache warm [--list NAME]` / `lc cache clear` | Pre-fetch a list for instant/offline use, or wipe the cache |
| `lc config [--lang L] [--editor CMD] [--solutions-dir DIR] [--list NAME] [--show]` | Settings |

The solve commands (`random`, `solve`, `daily`, `review`) also take:
`--lang cpp|java|go|rust|…`, `--hints`, and `--timebox MIN`. With `--timebox`, you get a desktop
notification when time's up (macOS, or Linux with `notify-send`), and the result
shows whether you finished within it.

`run`/`submit` find your solution in the solutions folder automatically; pass a
file to use a different one. The language comes from the file extension.

## Custom test cases

Every solution file has a test block. Add inputs one parameter per line, exactly
like LeetCode's testcase box, and `lc run` runs them along with the examples:

```python
# @tests — extra inputs for `lc run`: one parameter per line, as in LeetCode's testcase box
# [3,3]
# 6
# [-1,-2,-3,-4,-5]
# -8
# @end
```

The results table shows input, your output, expected output (computed by LeetCode)
and anything you `print()`ed, for every case.

## Spaced repetition

Your first accepted submit schedules a review for the next day. Each clean review
(accepted without a failed submit) pushes the next review out:
1 → 3 → 7 → 14 → 30 → 60 days. If you need more than one try, it goes back to 1 day.
Re-solving before the due date leaves the schedule as it is.

## Lists

Bundled: `questions` (15 classics, the default) and `neetcode150`. A list is a text
file with one URL or slug per line. `#` starts a comment, and comments containing `──`
become section headings in `lc list`. `--list` accepts a bundled name, a name
in `~/.leet/lists/`, or any file path. `lc add` never modifies the bundled files:
it copies them to `~/.leet/lists/` first.

## Where things live

```
~/.leet/config.json    cookies (chmod 600) + settings
~/.leet/history.json   every run/submit, solved state, review schedule
~/.leet/cache/         fetched problems
~/.leet/lists/         your lists
~/.leet/solutions/     solutions (change with: lc config --solutions-dir DIR)
```

Set `LEET_HOME` to use a different directory. The editor is `lc config --editor`,
else `$EDITOR`, else `vim`. GUI editors need a wait flag (e.g. `code -w`), or the
timer stops as soon as the editor opens.

## Development

```bash
pip install -e '.[dev]'
pytest
```

The code is in `leet/`: `cli.py` (commands), `api.py` (LeetCode client + cache),
`history.py` (progress + review scheduling), `display.py` (Rich output),
`templates.py` (solution files, `@tests`), `lists.py`, `languages.py`, `config.py`,
`timer.py`, `menu.py` (keyboard menus), `dashboard.py`. The tests never touch the network.
