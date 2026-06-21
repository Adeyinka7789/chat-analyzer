# Chat Insights App — Pre-Launch Audit

**Date:** 2026-06-14  
**Auditor:** Claude Code (diagnostic-only pass, no code changes made)  
**Scope:** Full codebase audit of `chat_analyzer` Django project

---

## Executive Summary — Top 5 Issues by Impact

1. **The privacy claim is false.** The badge in every page footer says "Private: Data never leaves memory." It does leave memory — Django file-based sessions write derived metrics (participant names, message counts, sentiment scores, etc.) to disk at `BASE_DIR/sessions/`. `settings.py:44` is the smoking gun. The raw chat text is not persisted, but participant identity data is. Fix this before launch or the claim needs to be reworded precisely.

2. **The processing page is pure theater built on top of a lie.** The entire analysis is complete before the user is even redirected to `/processing/`. The processing page runs four fake steps with deliberate `setTimeout` delays (2–3.5 seconds each, ~10–14 seconds total) and displays fabricated system metrics (random latency values, a fake "MEM_ALLOC" percentage, and "End-to-End Cryptographic Analysis Environment"). This is not a UX white lie — it actively deceives users about what the app does.

3. **CSRF protection is disabled on the only sensitive endpoint.** `views.py:12` decorates `upload_and_analyze` with `@csrf_exempt`, removing all cross-site request forgery protection from the POST endpoint that reads and processes user files.

4. **No file upload validation.** There is no file size limit anywhere — not in the view, not in the JS. A user (or attacker) can upload a 500 MB file and it will be read entirely into memory on the Django thread, blocking the server. The JS only checks for `.txt` extension (not MIME type).

5. **The emoji regex misses the most common emoji.** `parser.py:121` uses `[\U00010000-\U0010ffff]` to count emoji. This misses all BMP-range emoji, including ❤️ (U+2764), ✅ (U+2705), ⭐ (U+2B50), ✔️ (U+2714), and most symbol-style emoji that are extremely common in casual chat. The Text-to-Emoji Ratio metric and the Top Emojis feature are both wrong for most real chats.

---

## 1. Architecture Review

### Data Flow

```
User → dropzone.html → JS fetch POST /upload/ → upload_and_analyze() (views.py:13)
         ↓
    uploaded_file.read().decode('utf-8')   ← blocking, no size limit (views.py:16)
         ↓
    parse_whatsapp_file(content)            ← synchronous, no timeout (parser.py:9)
         ↓
    compute_all_metrics(messages, participants)  ← synchronous (parser.py:75)
         ↓
    request.session['analysis'] = metrics  ← written to disk (views.py:24)
         ↓
    return JsonResponse(metrics)            ← full metrics JSON to client
         ↓
    JS: sessionStorage.setItem('chatAnalysis', ...) (dropzone.html:~89)
         ↓
    window.location.href = '/processing/'
         ↓
    processing.html: fake 10–14s animation, then redirect to /dashboard/
         ↓
    dashboard() view: reads request.session.get('analysis') (views.py:29)
         ↓
    render(dashboard.html, {'data': json.dumps(analysis)}) (views.py:34)
         ↓
    {{ data|safe }} injected into JS (dashboard.html:227)
         ↓
    Alpine.js init(): parses JSON, renders ApexCharts
```

### Where Data Lives

| Data | Location | Persists? |
|---|---|---|
| Raw chat text | In-memory only, during request | No — discarded after parse |
| Derived metrics dict | `BASE_DIR/sessions/<session_key>` (file on disk) | Yes — until session expires |
| Full metrics JSON | Browser `sessionStorage` | Until tab is closed |
| Django logs | stdout (DEBUG=True may log request body) | Depends on deployment |

**Privacy claim assessment:** The raw message text does not persist, but derived data (participant names, message counts, initiation counts, latency scores, sentiment drift values, etc.) is serialized to disk by Django's file session backend. The badge text "Data never leaves memory" is inaccurate. A more honest claim would be: "Your chat text is never stored. Only anonymized statistics are kept for your session."

### Architectural Smells

- **Blocking request/response:** All parsing and metric computation (`parse_whatsapp_file` + `compute_all_metrics`) happens synchronously in the Django request thread (`views.py:17-20`). A large export (10,000+ messages) will block the thread for seconds. No async workers, no timeout.
- **Double storage of results:** The full metrics JSON is stored both in the Django server-side session (`views.py:24`) and in the browser's `sessionStorage` (`dropzone.html:~89`). The `sessionStorage` copy is never used — the dashboard reads from the server session. The client-side copy is dead code.
- **Dead routes:** `urls.py:9-11` defines three URL patterns (`analytics`, `history`, `agents`) that all alias `views.dashboard`. These are probably planned features — they silently return dashboard content, which would confuse a user who lands on `/agents/`.
- **Unused imports:** `views.py:5-6` imports `default_storage` and `ContentFile` but never uses either.

---

## 2. Parser Correctness

**File:** `analyzer/parser.py`

### Multi-line Messages — CRITICAL BUG

WhatsApp exports continuation lines (lines 2+ of a wrapped message) without any timestamp prefix. The parser's main loop unconditionally skips any line that doesn't match a timestamp pattern (`parser.py:55`: bare `continue`). This means every multi-line message is silently truncated to its first line. In typical conversational exports, 10–30% of messages may span multiple lines. Character counts, sentiment analysis, and any per-message text analysis are systematically wrong for these messages.

### Messages with Timestamps as Text Content

Not a practical issue: the regex requires the timestamp to appear at the very start of the line, so a message like "See you at 12/06/2026, 2:30 pm" is captured correctly as part of the text content (it appears after the sender+colon prefix, not at line start).

### Media/Attachment Placeholders

`parser.py:28` skips lines containing `<Media omitted>` or `Media omitted`. Correctly handled. However, media-heavy conversations will have distorted per-person message counts and participation ratios with no warning to the user.

### System Messages

Most system messages (group icon change, participant adds/removes, missed calls, group creation) don't contain a sender colon pattern and will simply fail both regexes, being silently dropped. Two are explicitly skipped (`This message was edited`, `This message was deleted`). The one risk: system messages that do match (unlikely but possible) could be misattributed as a sender named "Messages and calls are end-to-end encrypted". This is explicitly guarded for the E2E disclaimer but nothing else.

### Date/Time Format Coverage

**Only DD/MM/YYYY is supported.** `strptime` patterns at `parser.py:39` and `parser.py:50` are hardcoded to `%d/%m/%Y`. Consequences:

- **US format (MM/DD/YYYY):** Months 1–12 in the day position are valid dates, so January–December exports will parse but swap day and month silently. Days > 12 in the month position fail and are dropped. This is a silent, hard-to-detect data corruption.
- **iOS bracket format (`[DD/MM/YYYY, HH:MM:SS]`):** Not handled at all. iOS WhatsApp exports use `[date, time] Sender: message` with square brackets and seconds. Coverage: 0%.
- **Two-digit year:** Handled at `parser.py:59-61` by adding 2000. Correct for modern chats.
- **12h with optional space before am/pm:** Handled (`\s?` in pattern). The `%p` locale dependency in Python is a theoretical concern but practical on English-locale machines.

### Emoji and Non-Latin Scripts

Text content is stored as raw Unicode strings, so Arabic, Chinese, Yoruba, Igbo, etc. are preserved correctly in the messages list. However:

- **Sentiment analysis is English-only** — non-English chats always score 0 sentiment.
- **Emoji counting (`parser.py:121`)** uses `[\U00010000-\U0010ffff]` covering only supplementary plane code points. Missing: ❤️ (U+2764, BMP), ✅ (U+2705), ⭐ (U+2B50), ✔️ (U+2714), ☺ (U+263A), and all other BMP-range symbol/emoji characters. These are among the most commonly used in casual chat.
- **RTL text and Unicode control characters:** Arabic text may contain LRM/RLM markers (U+200E, U+200F) that are not stripped. This can affect word-boundary splitting in sentiment analysis (words may not match dictionary entries).

### Deleted Messages

`parser.py:27` — "This message was deleted" lines are explicitly skipped. Correct.

### Real-World Coverage Estimate

| Export type | Coverage |
|---|---|
| Android DD/MM/YYYY 12h | ~85% (multi-line truncation, emoji miscounting) |
| Android DD/MM/YYYY 24h | ~85% (same issues) |
| iOS bracket format | 0% (format not recognized) |
| US locale MM/DD/YYYY | ~60% (dates parse but month/day are swapped) |
| Non-English participant names | ~95% (Unicode names work fine) |
| Emoji-heavy chats | Emoji count wrong for BMP emoji |
| Non-English message text | Parsing OK, sentiment analysis always 0 |

---

## 3. Metrics Implementation Audit

### Initiation Rate (`parser.py:89–97`)

**Calculation:** Counts messages sent by a participant when the preceding message (by anyone) was more than 6 hours ago.

**Issues:**
- `init_A + init_B` may not equal total conversation starts. If both participants message within seconds after a 6h gap, only the first to message gets the initiation credit (correct behavior), but this is not documented or tested.
- If no conversations have a 6h gap (short test chats), both counts are 0. The denominator in `health` calculation becomes `(0 + 0 + 1) = 1` and `init_balance = 1.0`, treating "no initiations detected" as perfect balance. Misleading.
- **Group chats:** `compute_all_metrics:79` takes only the first two elements of `participants`. All other participants' messages are silently ignored in all per-person metrics. Initiation counts, message counts, latency, etc. are all wrong for groups.

### Response Latency (`parser.py:103–114`)

**Calculation:** Mean gap (seconds) from sender A's message to sender B's next reply, capped at 24h.

**Issues:**
- Returns `float('inf')` if no replies exist (e.g., one-sided conversation). This propagates into `latency_balance` calculation at `parser.py:202`:
  - `abs(inf - inf)` = `nan` (Python behavior)
  - `min(1, nan)` = `nan`
  - `1 - nan` = `nan`
  - `int(nan)` raises `ValueError` — **the health score crashes unhandled** if either participant never replies.
- The 24h cap (`86400`) is a magic number that should be a named constant.

### Text-to-Emoji Ratio (`parser.py:119–127`)

**Status:** Implemented but broken for BMP emoji. See Section 2. The formula `text_len_A / (emoji_A + 1)` is defensively guarded against division by zero, which is good.

### Midnight Oil Index (`parser.py:130–134`)

**Status:** Correctly implemented. Counts messages between 23:00 and 03:59 as a percentage. No issues.

### Sentiment Drift (`parser.py:136–155`)

**Calculation:** Compares average keyword sentiment between first half and second half of conversation.

**Issues:**
- Only 9 positive and 9 negative English words. No stemming ("loves" misses "love"). No negation handling ("not good" is counted as positive). Punctuation attached to words causes misses ("good," doesn't match "good").
- For non-English chats, no words ever match — both halves return 0, drift = 0. The summary says "Sentiment has declined over time" when drift is 0 or negative. A flat 0 will be reported as "declined" (`parser.py:221` uses `> 0` as the positive condition).
- The formula `(pos - neg) / (total + 1)` is bounded to approximately [-1, 1] and the normalization is reasonable but the inputs are too sparse to be meaningful.

### Ghosting Risk (`parser.py:157–174`)

**Issues:**
- Only checks pA→pB latency, not pB→pA. If pB is the one slowing down responses, it is not detected.
- On a 5-message chat, `last_10pct = max(1, int(5 * 0.1)) = 1`. The "last 10%" is a single message, making the comparison statistically meaningless.
- If `recent_lat_A_to_B = float('inf')` (B never replied in the last 10%) and `overall_lat_A_to_B = float('inf')`, then `inf > inf * 1.5` evaluates to `False` in Python, returning "Low" — wrong result for an actual non-reply scenario.

### Double-Text Count (`parser.py:176–182`)

**Status:** Correctly implemented. Counts consecutive same-sender messages within 5 minutes. The 5-minute window is a reasonable choice. The internal variable name "Desperation Index" is flagged in Section 6.

### Relationship Health Score (`parser.py:200–215`)

**Issues:**
- The `float('inf')` crash path noted in Response Latency applies here directly — `int(health)` will raise `ValueError` if either latency is inf.
- Equal 25% weighting for all four factors is arbitrary. A conversation where both people send 500 messages but one person initiates more will get penalized for initiation imbalance despite high mutual engagement.
- The verdict labels ("Needs Attention", "Distant Vibes") are discussed in Section 6.

### PRD Metrics vs. Implemented

| Metric | Status | Notes |
|---|---|---|
| Power Dynamic / Initiation Rate | ✅ Implemented | Group chat broken |
| Response Latency (per-direction) | ✅ Implemented | Crashes on inf |
| Text-to-Emoji Ratio | ⚠️ Implemented | BMP emoji missed |
| Midnight Oil Index | ✅ Correct | — |
| Sentiment Drift | ⚠️ Implemented | Naively; English-only |
| Double-Text Count | ✅ Correct | — |
| "Ghosting Risk" alert | ⚠️ Implemented | One-directional |
| Group chat support | ❌ Missing | Only first 2 participants used |
| Multi-line message handling | ❌ Missing | Lines silently dropped |
| iOS export format | ❌ Missing | 0% coverage |

---

## 4. UI/UX Gap Analysis

### 3-Page Flow Status

| Page | Template | Status |
|---|---|---|
| Dropzone (Page 1) | `dropzone.html` | Exists, functional |
| Engine Room (Page 2) | `processing.html` | Exists, entirely fake — see Section 6 |
| Showroom (Page 3) | `dashboard.html` | Exists, partial implementation |

### Premium vs. Generic

The visual design is genuinely premium-looking: custom dark theme, glassmorphism cards, custom font stack (Geist + Inter + JetBrains Mono), animated scanlines, Material Design 3 color tokens. The intent is clear and the aesthetic is well-executed.

**Implementation gaps that undercut the premium feel:**

- `dropzone.html` uses inline `style="..."` attributes throughout instead of Tailwind classes, inconsistent with the rest of the app.
- `dashboard.html:35–36`: The sidebar labels "Admin Console" and "Enterprise Tier" are wrong for a single-user free app. Creates cognitive dissonance.
- `dashboard.html:49`: "Upgrade Plan" button does nothing and has no href or click handler.
- `dashboard.html:26–27`: Settings gear icon has `@click="settingsOpen = true"` but no settings panel is implemented anywhere.
- `dropzone.html:12–14`: "Group Hustle" toggle exists in the UI and is styled, but the upload flow sends exactly the same `FormData` regardless of which mode is selected. The JS does not read `data-mode` anywhere. It is dead UI.

### Processing Animation (Full Inventory for Revision)

**File:** `processing.html:31–52`

The `processSteps` function runs a `for` loop with `setTimeout` delays:

```
Step 1: "Extracting cryptographic timestamps..."  — 2000–3500ms delay
Step 2: "Isolating unique conversational actors..."  — 2000–3500ms delay
Step 3: "Calculating response latencies & text ratios..."  — 2000–3500ms delay
Step 4: "Running linguistic emotion & ghosting risk algorithms..."  — 2000–3500ms delay
```

After Step 4 completes: 1000ms pause, then `window.location.href = '/dashboard/'`.

Total fake wait: approximately **9–15 seconds.**

The analysis is already complete (server returned `200 OK` with the full metrics JSON before the user was ever redirected to `/processing/`). The processing page is cosmetic only.

Additional fabricated readouts:
- `processing.html:107`: `'LATENCY: ' + (Math.floor(Math.random() * 40) + 12) + 'ms'` — random number, means nothing.
- `processing.html:110`: `'MEM_ALLOC: ' + (92 + currentStep * 2) + '%'` — increments with fake step counter, not measuring real memory.

### Charts and Visualizations

**Library:** ApexCharts (CDN)

| Chart | Element ID | Type | Notes |
|---|---|---|---|
| Relationship Health | `#relationshipHealthChart` | `radialBar` | 0–100% gauge |
| Volume Split | `#volumeSplitChart` | `donut` | 4 segments: A msgs, B msgs, A chars, B chars — confusing to combine two different metrics in one donut |
| Response Velocity | `#velocityChart` | horizontal `bar` | Shows average latency per person |
| Chronological Activity | `#chronologicalChart` | `area` | Hourly message counts, 24h x-axis |

Displayed as text only (no chart):
- Double-Text Index, Ghosting Risk, Hyper-Responder badge, Sentiment Drift

### Responsiveness

- Mobile navigation: none. The `aside` sidebar is `hidden md:flex` with no mobile fallback. On mobile, there is no navigation between any sections.
- Dropzone: `max-width: 600px; width: 100%` — responsive. Works on mobile.
- Dashboard chart containers: no explicit `height` on mobile. ApexCharts will auto-size but some charts may collapse on narrow viewports.
- The `px-margin-desktop` padding class is applied uniformly — on mobile this translates to 40px horizontal padding, which is too much for a 375px screen.

### Accessibility Gaps

- Settings button (`dashboard.html:26–27`): icon-only button, no `aria-label`.
- Close button in export modal (`dashboard.html:184`): icon-only, no `aria-label`.
- Export modal: missing `role="dialog"`, `aria-modal="true"`, and focus trap. Keyboard users cannot access or escape it cleanly.
- Emoji list items in emoji grid: contain only raw emoji characters — screen readers will announce emoji names but there is no count in accessible text.
- No `alt` attributes on SVG elements in `processing.html:56–61`.
- The scanline animation in `base.html` is decorative and not hidden from assistive technology (`pointer-events: none` but no `aria-hidden="true"`).

---

## 5. Code Quality & Structure

### Django App Structure

Standard single-app structure (`analyzer/`). Reasonable for a small project. No issues with file placement.

**Redundancies to clean up (not functionally harmful):**
- `analyzer/models.py`: empty except for Django boilerplate import. No models needed.
- `analyzer/admin.py`: empty. No models to register.
- `views.py:5-6`: `default_storage` and `ContentFile` imported but never used.
- `urls.py:9-11`: Three URL patterns aliasing `views.dashboard` — dead routes.

### Service Layer

`compute_all_metrics()` is a ~165-line monolithic function in `parser.py`. All metric calculations are nested functions inside it, making individual metrics impossible to unit-test in isolation and difficult to replace. The comment on `parser.py:73` says "no changes needed" — this suggests the function was written defensively against future modification rather than designed for it.

### Test Coverage

`analyzer/tests.py` — zero test cases. The boilerplate `# Create your tests here.` comment is the entire file.

**Critical untested paths:**
- Parser regex for all format variants (including multi-line truncation, which is the biggest silent bug)
- `compute_all_metrics` with a single participant, no replies, or a two-message conversation
- The `float('inf')` crash in health score calculation
- Upload endpoint: file size limits, wrong MIME type, malformed file content
- Session storage and retrieval across requests
- Group chat (3+ participants) — currently produces wrong results silently

### Hardcoded Magic Numbers

All of the following should be named constants or Django settings:

| Value | File:Line | Meaning |
|---|---|---|
| `6*3600` | `parser.py:93` | Conversation gap threshold (6 hours) |
| `86400` | `parser.py:111` | Max latency cap (24 hours) |
| `0.1` | `parser.py:158` | Ghosting risk window (last 10%) |
| `300` | `parser.py:181` | Double-text window (5 minutes) |
| `80`, `60`, `40` | `parser.py:208-212` | Health score tier thresholds |
| `5` | `views.py:18` | Minimum messages threshold |

### Config That Must Be Environment Variables Before Production

| Setting | File:Line | Issue |
|---|---|---|
| `SECRET_KEY` | `settings.py:6` | Hardcoded insecure key in plain text |
| `DEBUG` | `settings.py:7` | Must be `False` in production |
| `ALLOWED_HOSTS` | `settings.py:8` | Empty — rejects all non-localhost hosts |
| `SESSION_FILE_PATH` | `settings.py:45` | Should be configurable for deployment |

---

## 6. Framing & Copy Audit

The following instances require attention before launch. Each is flagged as one of three types: **[FALSE]** (factually wrong claim), **[THEATER]** (fabricated processing step), or **[FRAMING]** (anxiety-inducing or judgmental language).

---

**`base.html:~143`** — Privacy badge footer, every page  
> "Private: Data never leaves memory"  
**[FALSE]** — `settings.py:44` sets `SESSION_ENGINE = 'django.contrib.sessions.backends.file'`, which writes session data (participant names, all metric values) to disk at `BASE_DIR/sessions/`. The raw message text is not persisted, but derived personal data is. This claim is inaccurate as written and creates a false sense of privacy.

---

**`processing.html:33`**  
> "Extracting cryptographic timestamps..."  
**[THEATER]** — No cryptographic operation is performed. Timestamps are parsed with Python's `datetime.strptime`. This is a misleading label for a mundane text parsing operation.

---

**`processing.html:36`**  
> "Running linguistic emotion & ghosting risk algorithms..."  
**[THEATER]** — The linguistic analysis is a 9-word keyword lookup (`parser.py:141-142`). "Algorithms" (plural) is a stretch; "linguistic emotion" oversells what it is. This step is also already complete by the time this message displays.

---

**`processing.html:117`**  
> "End-to-End Cryptographic Analysis Environment"  
**[FALSE]** — There is no cryptography anywhere in this codebase. This copy was likely borrowed from a design template. It should be removed entirely.

---

**`processing.html:107`**  
> `'LATENCY: ' + (Math.floor(Math.random() * 40) + 12) + 'ms'`  
**[THEATER]** — Displayed as a live metric, this is a random integer between 12 and 52 with no relationship to any real measurement.

---

**`processing.html:110`**  
> `'MEM_ALLOC: ' + (92 + currentStep * 2) + '%'`  
**[THEATER]** — Fake memory allocation counter incrementing with the animation steps. Not measuring real memory.

---

**`parser.py:176`** — Variable name / internal comment  
> `# --- Double-Text Desperation Index ---`  
**[FRAMING]** — "Desperation" is a loaded, anxiety-inducing characterization of a neutral communication behavior (sending a follow-up message). This is an internal name but it surfaces in `dashboard.html:144` as the section label "Double Text Index" (the word "Desperation" is not in the UI currently, but the intent carries through). Worth cleaning up internally.

---

**`dashboard.html:148-153`**  
> "Ghosting Risk" section with "YELLOW ALERT" badge  
**[FRAMING]** — "Ghosting" is a charged relational term. A latency spike in the last 10% of messages has many innocent explanations (vacation, work deadline, a phone dying). Presenting this as a "YELLOW ALERT" with a `visibility_off` icon amplifies anxiety. The metric itself is also one-directional (only checks pA→pB, not pB→pA).

---

**`parser.py:208-215`** — Verdict labels fed into `summary` text  
> "Needs Attention", "Distant Vibes"  
**[FRAMING]** — These verdicts are presented as meaningful diagnoses but derive from a formula that weighs initiation balance, latency balance, message volume balance, and a 9-word sentiment score equally. A conversation where both people message equally but one person always texts first would score "Needs Attention." The labels imply more diagnostic validity than the underlying math supports.

---

**`dashboard.html:227`** — Template variable injection  
> `this.analysisData = {{ data|safe }};`  
**[Not framing — security note]** — `|safe` suppresses Django's auto-escaping and injects the raw JSON string directly into a `<script>` block. If participant names contained characters like `</script>` or `<!--`, this could be an XSS vector. The data comes from user-uploaded files, not external attackers, but this pattern should use `json_script` filter instead: `{% json_script data "analysis-data" %}` with `JSON.parse(document.getElementById('analysis-data').textContent)`.

---

## 7. Prioritized Punch List

### Critical (blocks launch or creates user trust problems)

- [ ] **Fix or reword the privacy claim** — either change the session engine to in-memory (`django.contrib.sessions.backends.cache`) or reword the badge to "Your messages are never stored. Session data expires when you close your browser."
- [ ] **Strip or reframe the processing page** — Remove false claims ("cryptographic", "End-to-End Cryptographic Analysis Environment", random metrics). Replace with accurate, honest copy about what is actually happening, or eliminate the fake steps entirely.
- [ ] **Add CSRF protection** — Remove `@csrf_exempt` from `upload_and_analyze` (`views.py:12`). Send the CSRF token in the JS fetch call (`X-CSRFToken` header, read from cookie).
- [ ] **Add file size validation** — Enforce a maximum upload size (e.g., 10 MB) in both the JS (before upload, `dropzone.html`) and the view (before `read()`, `views.py`).
- [ ] **Fix the float('inf') health score crash** — If `response_latency` returns `inf` for either direction, the health score calculation (`parser.py:202`) produces `nan`, and `int(nan)` raises `ValueError`. Guard against this.

### Important (significantly impacts metric accuracy or user experience)

- [ ] **Fix multi-line message truncation** — The parser needs to accumulate continuation lines (lines without a timestamp prefix) and append them to the previous message's text. This is the most impactful single parser fix.
- [ ] **Fix the emoji regex** — Replace `[\U00010000-\U0010ffff]` with the `emoji` library or a comprehensive Unicode regex pattern that covers BMP-range emoji (❤️, ✅, ⭐, etc.).
- [ ] **Handle iOS bracket format** — Add a third regex pattern for `[DD/MM/YYYY, HH:MM:SS] Sender: message`.
- [ ] **Fix `{{ data|safe }}` XSS risk** — Use Django's `{% json_script %}` template tag for safe JSON injection into `<script>` blocks (`dashboard.html:227`).
- [ ] **Remove or implement dead UI elements** — "Group Hustle" toggle, settings gear, "Upgrade Plan" button, "Admin Console / Enterprise Tier" labels, Export Report stub. Each is a broken promise in the UI.
- [ ] **Add group chat support or gate it clearly** — Currently `compute_all_metrics` silently uses only the first two participants. Either implement proper group metrics or detect group chats and show a "Group chats coming soon" message.
- [ ] **Fix ghosting risk to be bidirectional** — Currently only checks pA→pB latency trend (`parser.py:173`).
- [ ] **Move config to environment variables** — `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` must not be hardcoded (`settings.py:6-8`).
- [ ] **Fix `ALLOWED_HOSTS`** — An empty list will reject all non-localhost requests in production.

### Nice-to-Have (quality improvements for redesign pass)

- [ ] **Add test coverage** — At minimum: parser tests for multi-line messages, 12h/24h formats, system message skipping; metric tests for edge cases (no replies, single participant, 5-message minimum); view tests for upload validation.
- [ ] **Extract magic numbers to named constants** — The 6h gap, 24h cap, 5-minute double-text window, 10% ghosting window, and health thresholds are all scattered literals.
- [ ] **Add mobile navigation** — The dashboard sidebar is desktop-only with no mobile fallback.
- [ ] **Add aria-labels to icon-only buttons** — Settings icon, modal close button.
- [ ] **Add focus trap to export modal** — Required for keyboard accessibility.
- [ ] **Reframe anxiety-inducing copy** — "Ghosting Risk", "YELLOW ALERT", "Distant Vibes", "Needs Attention" should be rewritten for the redesign pass as curiosity-framing rather than threat-framing.
- [ ] **Consolidate `glass-card` CSS** — Currently redefined in `base.html`, `dashboard.html`, and `processing.html`. Should live in one place.
- [ ] **Remove unused imports** — `default_storage`, `ContentFile` in `views.py:5-6`.
- [ ] **Add bare-except cleanup** — `parser.py:40`, `parser.py:51` use bare `except:` clauses that catch `KeyboardInterrupt` and `SystemExit`. Should be `except ValueError:` at minimum.
- [ ] **Convert `dropzone.html` to Tailwind classes** — The page uses inline `style=""` attributes throughout, inconsistent with the rest of the codebase.
