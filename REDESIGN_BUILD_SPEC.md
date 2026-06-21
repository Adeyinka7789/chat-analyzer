# Chat Insights App — Redesign Build Spec

**Phase:** Post-audit redesign (visual system, theming, group mode, depth/AI-feel upgrades, zip/media upload)
**Prerequisite:** All "Critical" items from AUDIT.md should be fixed first (inf/nan crash, CSRF, file size limit, multi-line parser bug, privacy claim). If not yet done, fix those first — do not build new UI on top of a crashing parser.

---

## 1. Design System — "Obsidian Flux" (Dark + Light)

### 1.1 Convert all hardcoded colors to CSS custom properties

The Stitch-exported HTML hardcodes hex values throughout (`#000000`, `#0a0a0a`, `#00dce5`, `rgba(255,255,255,0.1)`, etc.) and uses a static Tailwind `colors` extend block. Replace this entirely:

- Define all design tokens as CSS custom properties on `:root` (dark, default) and `.light` (light override), e.g. `--surface`, `--surface-container`, `--on-surface`, `--primary-fixed`, `--secondary-container`, `--outline-variant`, etc.
- Reconfigure Tailwind's `colors.extend` to reference `var(--token-name)` instead of hex literals, so `bg-surface`, `text-primary-fixed`, etc. automatically respond to the active theme class.
- Theme toggle sets `class="dark"` or `class="light"` on `<html>`, persisted to `localStorage` (key: `theme`), applied on page load via a small inline script in `<head>` (before paint, to avoid flash-of-wrong-theme).

### 1.2 New accent color

Replace `#00dce5` (and its derived tokens `#00f5ff`, `#63f7ff`, `#00dce5` surface-tint/primary-fixed-dim) with a softer jade/teal: **`#5EEAD4`**.

Derive the full primary token set from this base using Material 3-style tonal logic (lighter "fixed" variants, darker "on-primary" variants, etc.) — same structural relationships as the original Obsidian Flux palette, just shifted to the new base hue. Keep secondary (pink `#ff4b89` family) and tertiary (emerald `#69f6b9` family) as-is — they pair fine with the new accent.

### 1.3 Dark theme tokens (default, `:root` / `.dark`)

Keep close to original Obsidian Flux values, with the accent swap above:

```css
:root {
  --surface: #131313;
  --surface-dim: #131313;
  --surface-bright: #3a3939;
  --surface-container-lowest: #0e0e0e;
  --surface-container-low: #1c1b1b;
  --surface-container: #201f1f;
  --surface-container-high: #2a2a2a;
  --surface-container-highest: #353534;
  --on-surface: #e5e2e1;
  --on-surface-variant: #b9caca;
  --outline: #849495;
  --outline-variant: #3a494a;
  --background: #131313;
  --on-background: #e5e2e1;

  /* New jade-based primary */
  --primary: #ecfdf9;
  --on-primary: #003c35;
  --primary-container: #5eead4;
  --on-primary-container: #00524a;
  --primary-fixed: #99f6e4;
  --primary-fixed-dim: #5eead4;
  --on-primary-fixed: #00201c;
  --on-primary-fixed-variant: #00504a;
  --surface-tint: #5eead4;

  /* Secondary (pink) — unchanged */
  --secondary: #ffb1c3;
  --on-secondary: #66002c;
  --secondary-container: #ff4b89;
  --on-secondary-container: #590026;
  --secondary-fixed: #ffd9e0;
  --secondary-fixed-dim: #ffb1c3;

  /* Tertiary (emerald) — unchanged */
  --tertiary: #eafff0;
  --on-tertiary: #003824;
  --tertiary-container: #69f6b9;
  --on-tertiary-container: #006f4c;
  --tertiary-fixed: #6ffbbe;
  --tertiary-fixed-dim: #4edea3;

  --error: #ffb4ab;
  --on-error: #690005;
  --error-container: #93000a;
  --on-error-container: #ffdad6;

  --glass-bg: rgba(10, 10, 10, 0.8);
  --glass-border: rgba(255, 255, 255, 0.1);
  --glass-gradient-start: rgba(255, 255, 255, 0.05);
  --glass-gradient-end: rgba(255, 255, 255, 0);
}
```

### 1.4 Light theme tokens (`.light`)

```css
.light {
  --surface: #fafaf9;
  --surface-dim: #ddd9d8;
  --surface-bright: #fafaf9;
  --surface-container-lowest: #ffffff;
  --surface-container-low: #f4f2f1;
  --surface-container: #eeebea;
  --surface-container-high: #e8e5e4;
  --surface-container-highest: #e2dfde;
  --on-surface: #1a1c1c;
  --on-surface-variant: #44494a;
  --outline: #74797a;
  --outline-variant: #c4c9ca;
  --background: #fafaf9;
  --on-background: #1a1c1c;

  --primary: #00504a;
  --on-primary: #ffffff;
  --primary-container: #5eead4;
  --on-primary-container: #00201c;
  --primary-fixed: #00504a;
  --primary-fixed-dim: #00695f;
  --on-primary-fixed: #ffffff;
  --on-primary-fixed-variant: #d6fbf2;
  --surface-tint: #00504a;

  --secondary: #8f0041;
  --on-secondary: #ffffff;
  --secondary-container: #ff4b89;
  --on-secondary-container: #3f0019;
  --secondary-fixed: #8f0041;
  --secondary-fixed-dim: #b3174f;

  --tertiary: #006f4c;
  --on-tertiary: #ffffff;
  --tertiary-container: #69f6b9;
  --on-tertiary-container: #002113;
  --tertiary-fixed: #005236;
  --tertiary-fixed-dim: #006f4c;

  --error: #ba1a1a;
  --on-error: #ffffff;
  --error-container: #ffdad6;
  --on-error-container: #410002;

  --glass-bg: rgba(255, 255, 255, 0.7);
  --glass-border: rgba(0, 0, 0, 0.08);
  --glass-gradient-start: rgba(0, 0, 0, 0.03);
  --glass-gradient-end: rgba(0, 0, 0, 0);
}
```

Adjust exact values during implementation for contrast (run through a contrast checker for text-on-surface combos — WCAG AA minimum for body text).

### 1.5 Glass card CSS — make theme-aware

```css
.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  border: 1px solid var(--glass-border);
  position: relative;
  overflow: hidden;
}
.glass-card::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, var(--glass-gradient-start) 0%, var(--glass-gradient-end) 100%);
  pointer-events: none;
}
```

Consolidate this single definition into `base.html` (or a shared CSS file) — currently redefined in 3 templates per the audit.

### 1.6 Theme toggle component

Place in nav bar (replace the `palette` settings icon stub, or repurpose it). Simple sun/moon icon toggle, not a full "Theme Config" panel with accent-color pickers (the Stitch design's "Theme Config" overlay with custom accent swatches and "Interface Density" dropdown is over-scoped for v1 — drop it; ship a clean dark/light toggle only).

```js
// inline in <head>, before paint
(function() {
  const saved = localStorage.getItem('theme');
  const theme = saved || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  document.documentElement.className = theme;
})();
```

```js
// toggle handler
function toggleTheme() {
  const next = document.documentElement.className === 'dark' ? 'light' : 'dark';
  document.documentElement.className = next;
  localStorage.setItem('theme', next);
  window.dispatchEvent(new CustomEvent('theme-changed', { detail: next }));
}
```

### 1.7 ApexCharts theme-awareness

Every chart instance must listen for `theme-changed` and call `updateOptions` with a recomputed palette + grid color + `theme.mode`. Build a single helper:

```js
function getChartTheme() {
  const isDark = document.documentElement.className === 'dark';
  return {
    mode: isDark ? 'dark' : 'light',
    gridColor: isDark ? '#1A1A1A' : '#E5E5E5',
    palette: isDark
      ? ['#5eead4', '#ff4b89', '#69f6b9', '#849495']
      : ['#00695f', '#b3174f', '#006f4c', '#74797a']
  };
}
```

On `theme-changed`, loop all chart instances: `chart.updateOptions({ theme: { mode }, grid: { borderColor: gridColor }, colors: palette })`.

---

## 2. Drop dead/misleading UI from Stitch exports

When porting Stitch templates to Django, remove:
- "Admin Console" / "Enterprise Tier" sidebar header
- "Upgrade Plan" button
- "Theme Config" overlay's accent-color picker grid and "Interface Density" dropdown (replaced by simple dark/light toggle above)
- Top nav "Agents" link and sidebar "Agents" / "History" items (unless these are real planned routes — if not, remove entirely, don't alias to dashboard)
- "Export Data" button on `engine_analytics` unless wired to the real export modal
- Any `account_circle` profile icon (no auth/accounts in this app)

---

## 3. WhatsApp ZIP + media upload handling

### 3.1 Dropzone changes

- Accept `.zip` in addition to `.txt` (update both the `accept` attribute and any client-side extension check).
- Update dropzone copy: "Drop your WhatsApp export here (.txt or .zip)".

### 3.2 Server-side processing (`views.py`)

```python
import zipfile
import io

def extract_chat_text(uploaded_file):
    """
    Accepts an UploadedFile that is either a .txt or a .zip
    (WhatsApp 'Export Chat' with media). Returns decoded chat text.
    Media files are read only to confirm presence/count, never persisted.
    """
    filename = uploaded_file.name.lower()

    if filename.endswith('.zip'):
        with zipfile.ZipFile(uploaded_file) as zf:
            # Validate zip bomb risk: check total uncompressed size before extracting
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > MAX_UNCOMPRESSED_SIZE:  # e.g. 50 MB
                raise ValueError("Archive too large")

            # Find the chat text file — iOS exports use "_chat.txt",
            # Android exports use "WhatsApp Chat with <Name>.txt" or similar
            txt_candidates = [
                n for n in zf.namelist()
                if n.lower().endswith('.txt') and not n.startswith('__MACOSX')
            ]
            if not txt_candidates:
                raise ValueError("No chat text file found in archive")

            # Prefer _chat.txt (iOS convention) if present, else first match
            chat_file = next(
                (n for n in txt_candidates if n.lower().endswith('_chat.txt')),
                txt_candidates[0]
            )

            with zf.open(chat_file) as f:
                content = f.read().decode('utf-8')

            # Count media files for "Media-Heavy Conversation" stat —
            # do NOT extract or persist them
            media_count = len(zf.namelist()) - len(txt_candidates)
            return content, media_count

    else:
        content = uploaded_file.read().decode('utf-8')
        return content, 0
```

### 3.3 File size limits (Critical from audit, applies here too)

- `.txt`: max 10 MB
- `.zip`: max 50 MB *uncompressed* total (check `infolist()` sizes before reading any member — protects against zip bombs)
- Enforce both client-side (JS, before upload — read `file.size`) and server-side (before any `.read()`/`zipfile.ZipFile()` call)

### 3.4 Parser: media placeholder handling per locale

Android exports: `‎<attached: IMG-20240101-WA0001.jpg>` or `<Media omitted>`
iOS exports: `‎image omitted`, `‎video omitted`, `‎audio omitted`, `‎sticker omitted`, `‎GIF omitted`, `‎Contact card omitted`

Update the media-skip check in `parser.py` to a regex covering all these variants (case-insensitive), and **count them per participant** as a new "Media Shared" stat per person rather than silently dropping with no trace — this becomes a Textual DNA card stat ("Sam shared 142 media files").

### 3.5 iOS bracket date format (already on audit punch list — needed now for zip support since iOS exports are zip-only)

Add a third regex pattern for:
```
[DD/MM/YYYY, HH:MM:SS] Sender: message
```
alongside the existing two Android patterns. Try all three in order during parsing.

---

## 4. Conversation Mode: 1v1 vs Group

### 4.1 Dropzone toggle — wire it up

The Stitch dropzone already has a "PERSONAL CHAT (1V1)" / "GROUP HUSTLE" segmented control (`chatType` Alpine state) but it's currently decorative. Wire it:

- Send `chat_type` (`'1v1'` or `'group'`) as a form field alongside the file upload.
- Server validates: after parsing, count actual unique participants. If `chat_type == '1v1'` but >2 participants detected, show a non-blocking notice on the dashboard: "This looks like a group chat — switch to Group view for per-person breakdowns." (Don't hard-block; just inform.)
- If `chat_type == 'group'` but only 2 participants detected, group mode still works (it's a superset) — just less interesting.

### 4.2 `compute_all_metrics` — branch by mode

Refactor the current monolithic function into:

```python
def compute_metrics(messages, participants, chat_type):
    if chat_type == '1v1' and len(participants) == 2:
        return compute_1to1_metrics(messages, participants)
    return compute_group_metrics(messages, participants)
```

**`compute_1to1_metrics`** — existing logic (initiation rate, response latency A↔B, text-to-emoji ratio per person, etc.), with the bug fixes from AUDIT.md Section 3 (the `inf`/`nan` crash guard especially).

**`compute_group_metrics`** — new, per-participant leaderboards instead of A vs B comparisons:

| Metric | 1:1 version | Group version |
|---|---|---|
| Initiation Rate | A vs B % split | "Conversation Starters" leaderboard — % of post-6h-gap messages per person, ranked |
| Response Latency | A→B avg, B→A avg | "Average time-to-first-reply" per person (time between someone posting and that person's next message in the thread) — ranked, lowest = "Fastest Responder" |
| Text-to-Emoji Ratio | per person, 2 cols | per person, ranked list (existing emoji fix from audit applies) |
| Midnight Oil Index | overall % | overall % (unchanged — works for any N) |
| Sentiment Drift | overall | overall (unchanged) |
| Double-Text Count | per person | per person, ranked |
| Ghosting Risk / Response Pattern Shift | A↔B directional | **dropped for groups** — doesn't map meaningfully to N people. Replace with "Most Active This Week vs Last Week" shift per person |
| Health Score (single 0-100) | dropped per Section 6 reframe anyway | N/A |
| Message Volume Split | donut, A vs B | bar chart, all N participants ranked by message count |
| Group-only: "Quietest Member" | — | participant with fewest messages / longest average reply time |
| Group-only: "Group Pulse" | — | messages-per-day trend line, whole group |

### 4.3 Dashboard template variants

Two dashboard layouts sharing the same shell/nav/theme system:

- `dashboard_1v1.html` — port of `the_showroom_insights_engine_desktop` / `_mobile` (two-column comparisons, Volume Split donut, Response Velocity bar, Emoji Grid two-column)
- `dashboard_group.html` — new layout using ranked list/leaderboard components for each metric above. Borrow visual language from `engine_analytics_desktop_advanced` (the card grid, sparklines, AI insight callouts) but replace the 2-series charts with N-series or ranked-bar versions.

View selects template based on `chat_type` stored with the analysis result.

---

## 5. Depth & "AI Feel" — New/Reworked Dashboard Cards

All of these compute from data already available in the parsed message list — no actual LLM calls required, but copy is phrased as a synthesized observation (see 5.5).

### 5.1 "Textual DNA" card

Per participant (1:1: two columns; group: ranked list):
- Average words per message
- Average characters per message
- Vocabulary richness: unique words ÷ total words (rounded %)
- Media files shared (from 3.4)
- Sparkline: avg message length over time (binned weekly/monthly depending on chat duration)

### 5.2 "Conversation Rhythm" card

Whole-conversation stats:
- Most active day of week (bar chart, 7 bars)
- Most active hour of day (24-bar chart — can reuse/extend existing Chronological Activity chart)
- Longest active streak: consecutive calendar days with ≥1 message
- Longest silence: largest gap between consecutive messages (display as "X days, Y hours")
- Total conversation span (first message date → last message date)

### 5.3 "Sync Snapshot" (replaces single Health Score gauge)

Instead of one 0-100 verdict number, show 3-4 small stat tiles with neutral framing:
- Total messages exchanged
- Average messages per day (over conversation span)
- Most active month
- Response balance (e.g., "Replies are fairly even" / "One person tends to message more" — descriptive, not scored)

### 5.4 "Power Dynamics" card (from `engine_analytics_desktop_advanced`, reframed)

- Balance bar: "Who breaks the silence" — % of conversation-starting messages per person (1:1: two segments; group: stacked bar per person)
- Keep the visual style (progress bars with glow) but drop "Agent/User" framing entirely — use actual participant names

### 5.5 AI Insight callouts — real computed observations, framed as synthesis

Small panel with `auto_awesome` icon and label "Pattern Detected" (not "Proximity AI Insight" — avoid implying a specific AI brand/product). One templated sentence per card, generated from a small rules-based template bank using the actual computed numbers. Examples:

```python
def generate_insight(metrics, chat_type):
    insights = []

    if metrics['midnight_oil_pct'] > 30:
        insights.append(
            f"Over {metrics['midnight_oil_pct']}% of messages happen between "
            f"11pm and 4am — this conversation has a strong late-night rhythm."
        )

    if metrics.get('peak_day'):
        insights.append(
            f"{metrics['peak_day']} is consistently the busiest day, "
            f"suggesting a regular weekly pattern."
        )

    if chat_type == '1v1':
        balance = metrics['initiation_balance']  # 0.0-1.0
        if balance > 0.7:
            insights.append(
                f"{metrics['top_initiator']} starts the majority of conversations "
                f"after periods of silence — a fairly one-sided initiation pattern."
            )
        elif balance < 0.55:
            insights.append(
                "Both participants initiate conversations about equally often."
            )

    # ... more rules per available metric

    return insights[:3]  # cap at 3 per page, rotate/prioritize by "interestingness"
```

This keeps the "AI feel" (synthesized-sounding prose, `auto_awesome` iconography, "Pattern Detected" framing) while being 100% truthful — every sentence is directly traceable to a computed number. No fabricated confidence, no theater.

### 5.6 Reframed/renamed existing cards (per earlier copy discussion)

| Old (Stitch/current) | New |
|---|---|
| "The Verdict" + single Health Score gauge | "Sync Snapshot" (5.3) |
| "Ghosting Risk" / "YELLOW ALERT" | "Response Pattern Shift" — neutral description, e.g. "Sam's replies have slowed down recently — could be a busy week" |
| "Double Text Index" / "Desperation threshold exceeded" | "Quick Follow-ups" — "Alex sends follow-up messages 14% more often this week" |
| "Hyper-Responder" / "BADGE EARNED" | Keep as a positive badge but drop game-ification framing — "Fast Responder: sub-5-min replies for 48 hours straight" |
| "Tone Shift Detector" / "SENTIMENT" badge | "Tone Over Time" — part of Sentiment Drift card, not a standalone alert |

---

## 6. Processing page rework — keep the design, make it real (ties to AUDIT.md Critical items)

The Engine Room visual design (glass-card layout, terminal-style step list, glow/animation aesthetic) stays. What changes is that **every step shown must correspond to a real, currently-executing stage of the analysis** — no scripted delays, no fabricated readouts.

### 6.1 Architecture: server does real work in stages, client reflects real progress

Move analysis out of a single synchronous request/response. Two viable approaches depending on effort budget:

**Approach 1 — Synchronous-with-staged-response (simplest, no Celery needed)**

The upload endpoint performs the real stages in order — extract/parse, compute metrics, (for 1:1: compute health/sync stats; for group: compute leaderboards) — and the client shows the Engine Room page *while this single request is in flight*, with the step list advancing based on actual elapsed sub-timings reported back, OR simply showing each step as "in progress" until the response returns, then marking all complete at once.

If the whole thing takes <1s, the honest UI is: show step 1 as active immediately, and when the response arrives, mark all steps complete in quick succession (each genuinely "completing" within the same ~100-300ms window) rather than spacing them out artificially. This is still truthful — the work *did* happen, just fast. Don't add `setTimeout` delays to slow it down for effect.

**Approach 2 — Real async with task polling (if you want true per-stage progress, or for large files)**

- Upload endpoint kicks off a Celery task and returns a `task_id` immediately.
- Engine Room page polls `/task-status/<task_id>/` every ~300-500ms.
- The Celery task updates its own state at each real stage:
  ```python
  @shared_task(bind=True)
  def analyze_chat_task(self, content, chat_type):
      self.update_state(state='PROGRESS', meta={'stage': 'parsing', 'detail': 'Parsing messages...'})
      messages, participants = parse_whatsapp_file(content)

      self.update_state(state='PROGRESS', meta={'stage': 'metrics', 'detail': f'Computing metrics for {len(participants)} participants...'})
      metrics = compute_metrics(messages, participants, chat_type)

      self.update_state(state='PROGRESS', meta={'stage': 'insights', 'detail': 'Generating insights...'})
      metrics['insights'] = generate_insight(metrics, chat_type)

      return metrics
  ```
- Engine Room JS maps `meta.stage` to the corresponding step in the UI and marks it complete only when the poll response shows that stage has passed. The step list length should match the actual number of distinct stages — don't pad with extra cosmetic steps.

### 6.2 Honest copy for each real stage

| Old (fabricated) | New (real) |
|---|---|
| "Extracting cryptographic timestamps..." | "Parsing messages..." |
| "Isolating unique conversational actors..." | "Identifying participants..." |
| "Calculating response latencies & text ratios..." | "Computing metrics..." |
| "Running linguistic emotion & ghosting risk algorithms..." | "Generating insights..." |

Each label should only appear/complete when that actual code path is running/has finished. If a stage doesn't exist as a separate step in the implementation (e.g. participant identification happens inside parsing, not as a separate pass), don't show it as a separate step — collapse to however many real stages actually exist.

### 6.3 Remove entirely — no honest equivalent

- "End-to-End Cryptographic Analysis Environment" label
- `'LATENCY: ' + (Math.floor(Math.random() * 40) + 12) + 'ms'`
- `'MEM_ALLOC: ' + (92 + currentStep * 2) + '%'`

If you want *some* live-feeling readout in that space, use something real and cheap to compute, e.g. actual message count as it's parsed (`'MESSAGES PARSED: 4,212'`) or actual elapsed time (`'ELAPSED: 0.34s'`) — both are true, both look technical, neither is fake.

### 6.4 Recommended approach for this app

Given typical file sizes (10MB txt / 50MB zip uncompressed, parses in well under a second with the multi-line fix applied), **Approach 1** is sufficient — no Celery needed for v1. The Engine Room page still gets shown (preserving the design), but its step list reflects a single fast real request, with steps completing in quick honest succession rather than over a scripted 9-15 seconds. If file sizes grow significantly later (e.g. multi-year group chat exports with 100k+ messages), revisit Approach 2.

---

## 7. Export (PDF/image) — theme-aware

- Export modal gains no new controls; it inherits the dashboard's current theme.
- If using WeasyPrint (per docx/pdf skill conventions) for PDF generation: pass the active theme as a template context variable, and maintain two stylesheet variants (or one stylesheet with the CSS-variable approach from Section 1, since WeasyPrint supports CSS custom properties).
- If using client-side capture (html2canvas / browser print): no extra work needed — it captures whatever theme is currently rendered.
- "Spotify Wrapped"-style shareable export screens (`the_showroom_*_spotify_wrapped_export`) should also respect the toggle — these are likely the most-shared artifact, so getting the light variant right matters for users who prefer it.

---

## 8. Build Order

1. Design tokens + CSS variable conversion + theme toggle (Section 1) — foundation for everything else
2. Drop dead UI elements (Section 2)
3. Processing page rework (Section 6) — quick win, removes the theater
4. ZIP/media upload + iOS format support (Section 3)
5. Group vs 1v1 toggle wiring + metrics branch (Section 4)
6. New depth cards: Textual DNA, Conversation Rhythm, Sync Snapshot, Power Dynamics, AI Insights (Section 5)
7. Reframed copy pass across all cards (Section 5.6)
8. Theme-aware exports (Section 7)

Each step should be testable independently — don't combine steps 4-6 into one giant commit, since group-mode metrics depend on the parser fixes from step 4.
