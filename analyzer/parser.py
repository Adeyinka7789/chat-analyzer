import re
import sys
import math
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics

from emoji import emoji_list as _emoji_list


def extract_emojis(text: str) -> list[str]:
    """All emoji in `text`, in order. Uses the `emoji` library so BMP emoji
    (❤ ☺ ✨ ✅ ☀ 👍 …) are caught — the old [\\U00010000-\\U0010ffff] regex
    missed every emoji in the Basic Multilingual Plane."""
    return [e['emoji'] for e in _emoji_list(text)]


def count_emojis(text: str) -> int:
    return len(extract_emojis(text))


# ─────────────────────────────────────────────────────────────
# ENHANCED METRICS HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────

def compute_word_battle(msgs_A, msgs_B):
    """Word Battle Arena metrics"""
    avg_words_A = statistics.mean([len(m['text'].split()) for m in msgs_A]) if msgs_A else 0
    avg_words_B = statistics.mean([len(m['text'].split()) for m in msgs_B]) if msgs_B else 0
    
    longest_A = max([len(m['text']) for m in msgs_A]) if msgs_A else 0
    longest_B = max([len(m['text']) for m in msgs_B]) if msgs_B else 0
    
    words_A = set()
    words_B = set()
    for m in msgs_A:
        words_A.update([w.lower().strip(".,!?;:'\"") for w in m['text'].split() if w])
    for m in msgs_B:
        words_B.update([w.lower().strip(".,!?;:'\"") for w in m['text'].split() if w])
    
    return {
        'avg_words': [round(avg_words_A, 1), round(avg_words_B, 1)],
        'longest_message': [longest_A, longest_B],
        'unique_words': [len(words_A), len(words_B)]
    }


def compute_word_histogram(msgs_A, msgs_B):
    """Word count distribution bins"""
    bins = [(0, 5), (6, 15), (16, 30), (31, 50), (51, float('inf'))]
    
    def bin_counts(msgs):
        counts = [0] * len(bins)
        for m in msgs:
            word_count = len(m['text'].split())
            for i, (low, high) in enumerate(bins):
                if low <= word_count <= high:
                    counts[i] += 1
                    break
        return counts
    
    return [bin_counts(msgs_A), bin_counts(msgs_B)]


def compute_question_ratio(msgs_A, msgs_B):
    """Percentage of messages that are questions"""
    def is_question(text):
        if '?' in text:
            return True
        first_word = text.lower().split()[0] if text.split() else ''
        question_starts = {'what', 'who', 'where', 'when', 'why', 'how', 'do', 'does', 'did', 'is', 'are', 'was', 'were', 'can', 'could', 'would', 'should'}
        return first_word in question_starts
    
    questions_A = sum(1 for m in msgs_A if is_question(m['text']))
    questions_B = sum(1 for m in msgs_B if is_question(m['text']))
    
    # Returned as 0.0-1.0 fractions; the UI multiplies by 100 for display.
    return [
        round(questions_A / len(msgs_A), 3) if msgs_A else 0,
        round(questions_B / len(msgs_B), 3) if msgs_B else 0
    ]


def compute_abbrev_density(msgs_A, msgs_B):
    """Percentage of messages containing common abbreviations"""
    abbreviations = {'lol', 'lmao', 'omg', 'wtf', 'btw', 'imo', 'tbh', 'idk', 'idc', 'smh', 'fyi', 'np', 'ty', 'brb', 'gtg', 'pls', 'plz', 'thx', 'u', 'ur'}
    
    def density(msgs):
        if not msgs:
            return 0
        count = 0
        for m in msgs:
            words = set(w.lower().strip(".,!?;:'\"") for w in m['text'].split() if w)
            if words & abbreviations:
                count += 1
        return round((count / len(msgs)) * 100, 1)
    
    return [density(msgs_A), density(msgs_B)]


def compute_sentiment_volatility(messages):
    """Standard deviation of sentiment scores over time"""
    positive_words = {'love', 'nice', 'good', 'great', 'happy', 'amazing', 'awesome', 'bless', 'proud'}
    negative_words = {'hate', 'bad', 'sad', 'angry', 'annoying', 'awful', 'terrible', 'sorry', 'hurt'}
    
    scores = []
    window_size = max(10, len(messages) // 20) if len(messages) > 20 else 5
    if window_size < 2:
        return 0
    
    for i in range(0, len(messages) - window_size + 1, max(1, window_size // 2)):
        window = messages[i:i+window_size]
        pos = neg = 0
        for m in window:
            words = set(m['text'].lower().split())
            pos += len(words & positive_words)
            neg += len(words & negative_words)
        score = (pos - neg) / (pos + neg + 1)
        scores.append(score)
    
    return statistics.stdev(scores) if len(scores) > 1 else 0


def compute_positivity_ratio(messages):
    """Percentage of messages that are predominantly positive"""
    positive_words = {'love', 'nice', 'good', 'great', 'happy', 'amazing', 'awesome', 'bless', 'proud'}
    
    positive_count = 0
    for m in messages:
        words = set(m['text'].lower().split())
        if words & positive_words:
            positive_count += 1
    
    # Returned as a 0.0-1.0 fraction; the UI multiplies by 100 for display.
    return round(positive_count / len(messages), 3) if messages else 0


def compute_sentiment_over_time(messages):
    """Sentiment score trend over time"""
    positive_words = {'love', 'nice', 'good', 'great', 'happy', 'amazing', 'awesome', 'bless', 'proud'}
    negative_words = {'hate', 'bad', 'sad', 'angry', 'annoying', 'awful', 'terrible', 'sorry', 'hurt'}
    
    week_scores = defaultdict(list)
    for m in messages:
        week_key = m['timestamp'].strftime('%Y-W%W')
        words = set(m['text'].lower().split())
        pos = len(words & positive_words)
        neg = len(words & negative_words)
        score = (pos - neg) / (pos + neg + 1)
        week_scores[week_key].append(score)
    
    result = []
    for week in sorted(week_scores.keys())[:20]:
        avg_score = statistics.mean(week_scores[week])
        result.append({
            'week': week,
            'score': round(avg_score, 3)
        })
    
    return result


def compute_burstiness_score(messages):
    """Measure of message clustering (0=regular, 1=bursty)"""
    if len(messages) < 3:
        return 0
    
    intervals = []
    for i in range(1, len(messages)):
        delta = (messages[i]['timestamp'] - messages[i-1]['timestamp']).total_seconds() / 60
        if delta > 0:
            intervals.append(delta)
    
    if not intervals:
        return 0
    
    mean_interval = statistics.mean(intervals)
    if mean_interval == 0:
        return 0
    
    std_interval = statistics.stdev(intervals) if len(intervals) > 1 else 0
    cv = std_interval / mean_interval
    burstiness = min(1, cv / 3)
    return round(burstiness, 2)


def compute_predictability_score(messages):
    """How regular are messaging patterns"""
    if len(messages) < 20:
        return 0
    
    hour_dist = [0] * 24
    for m in messages:
        hour_dist[m['timestamp'].hour] += 1
    
    total = len(messages)
    entropy = 0
    for count in hour_dist:
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    
    max_entropy = math.log2(24)
    predictability = 100 * (1 - (entropy / max_entropy))
    return round(predictability, 1)


def compute_best_time_to_message(msgs_person):
    """Find best 2-hour window for messaging"""
    if len(msgs_person) < 10:
        return "Insufficient data"
    
    hour_counts = [0] * 24
    for m in msgs_person:
        hour_counts[m['timestamp'].hour] += 1
    
    best_hour = 0
    best_count = 0
    for i in range(24):
        window_count = hour_counts[i] + hour_counts[(i+1) % 24]
        if window_count > best_count:
            best_count = window_count
            best_hour = i
    
    start = best_hour
    end = (best_hour + 2) % 24
    
    def format_hour(h):
        if h == 0:
            return "12am"
        elif h < 12:
            return f"{h}am"
        elif h == 12:
            return "12pm"
        else:
            return f"{h-12}pm"
    
    if start < end:
        return f"{format_hour(start)}–{format_hour(end)}"
    else:
        return f"{format_hour(start)}–{format_hour(end)}"


def compute_turn_equality(messages, participants):
    """Measure conversation balance (0-100%)"""
    if len(messages) < 2 or len(participants) != 2:
        return 50
    
    p1, p2 = participants[0], participants[1]
    p1_count = sum(1 for m in messages if m['sender'] == p1)
    p2_count = sum(1 for m in messages if m['sender'] == p2)
    total = p1_count + p2_count
    
    if total == 0:
        return 50
    
    p1_pct = p1_count / total
    balance = 100 - abs(p1_pct - 0.5) * 200
    return round(balance, 1)


def compute_peak_hour_text(hourly_total):
    """Get readable peak hour"""
    if not hourly_total or sum(hourly_total) == 0:
        return "N/A"
    peak_hour = max(range(24), key=lambda i: hourly_total[i])
    if peak_hour == 0:
        return "12am"
    elif peak_hour < 12:
        return f"{peak_hour}am"
    elif peak_hour == 12:
        return "12pm"
    else:
        return f"{peak_hour-12}pm"


def compute_best_day_text(rhythm):
    """Get best day from rhythm data"""
    if not rhythm or not rhythm.get('day_counts'):
        return "N/A"
    day_counts = rhythm['day_counts']
    if sum(day_counts) == 0:
        return "N/A"
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    best_idx = max(range(7), key=lambda i: day_counts[i])
    return day_names[best_idx]


# ─────────────────────────────────────────────────────────────
# EXISTING HELPER FUNCTIONS (Keep these as is)
# ─────────────────────────────────────────────────────────────

def _textual_dna(msgs):
    """Avg words/chars, vocabulary richness, sparkline of avg length over time."""
    if not msgs:
        return {'avg_words': 0.0, 'avg_chars': 0.0, 'vocab_richness': 0.0, 'length_over_time': []}
    word_counts = [len(m['text'].split()) for m in msgs]
    char_counts = [len(m['text']) for m in msgs]
    all_words = [w.lower().strip(".,!?;:'\"") for m in msgs for w in m['text'].split() if w]
    richness = round(len(set(all_words)) / len(all_words) * 100, 1) if all_words else 0.0
    span_days = (msgs[-1]['timestamp'] - msgs[0]['timestamp']).days if len(msgs) > 1 else 0
    bins = defaultdict(list)
    for m in msgs:
        key = m['timestamp'].strftime('%Y-%m') if span_days > 90 else m['timestamp'].strftime('%Y-W%W')
        bins[key].append(len(m['text']))
    length_over_time = [[k, round(statistics.mean(v), 1)] for k, v in sorted(bins.items())]
    return {
        'avg_words': round(statistics.mean(word_counts), 1),
        'avg_chars': round(statistics.mean(char_counts), 1),
        'vocab_richness': richness,
        'length_over_time': length_over_time,
    }


def _conversation_rhythm(messages):
    """Day-of-week counts, hour counts, streak, silence gap, span."""
    if not messages:
        return {}
    day_counts = [0] * 7
    hour_counts = [0] * 24
    for m in messages:
        day_counts[m['timestamp'].weekday()] += 1
        hour_counts[m['timestamp'].hour] += 1
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    peak_day = day_names[day_counts.index(max(day_counts))] if any(day_counts) else "Unknown"
    all_dates = sorted(set(m['timestamp'].date() for m in messages))
    longest_streak = current_streak = 1
    for i in range(1, len(all_dates)):
        if (all_dates[i] - all_dates[i - 1]).days == 1:
            current_streak += 1
            if current_streak > longest_streak:
                longest_streak = current_streak
        else:
            current_streak = 1
    max_gap = timedelta(0)
    for i in range(1, len(messages)):
        gap = messages[i]['timestamp'] - messages[i - 1]['timestamp']
        if gap > max_gap:
            max_gap = gap
    span = messages[-1]['timestamp'] - messages[0]['timestamp']
    return {
        'day_counts': day_counts,
        'hour_counts': hour_counts,
        'peak_day': peak_day,
        'longest_streak_days': longest_streak,
        'longest_silence_days': max_gap.days,
        'longest_silence_hours': max_gap.seconds // 3600,
        'span_days': span.days,
        'first_date': messages[0]['timestamp'].strftime('%b %d, %Y'),
        'last_date': messages[-1]['timestamp'].strftime('%b %d, %Y'),
    }


def compute_sessions(messages, gap_hours=4):
    """Split a chronological message list into conversation sessions.

    A new session begins whenever the gap to the previous message exceeds
    `gap_hours`. The very first message always opens session 1. Returns a list of
    session dicts: start_dt, end_dt, msg_count, initiator (first sender), ender
    (last sender), duration_minutes.
    """
    if not messages:
        return []

    gap_seconds = gap_hours * 3600
    groups = [[messages[0]]]
    for prev, cur in zip(messages, messages[1:]):
        if (cur['timestamp'] - prev['timestamp']).total_seconds() > gap_seconds:
            groups.append([cur])
        else:
            groups[-1].append(cur)

    sessions = []
    for g in groups:
        start, end = g[0]['timestamp'], g[-1]['timestamp']
        sessions.append({
            'start_dt': start,
            'end_dt': end,
            'msg_count': len(g),
            'initiator': g[0]['sender'],
            'ender': g[-1]['sender'],
            'duration_minutes': round((end - start).total_seconds() / 60, 1),
        })
    return sessions


def _fmt_minutes(m):
    """Human-readable reply latency, matching the dashboard's formatMins()."""
    if m is None:
        return "an unknown time"
    mins = int(m)
    secs = int(round((m - mins) * 60))
    return f"{mins}m {secs}s" if mins > 0 else f"{secs}s"


def _group_insights(metrics):
    """4–6 plain-string observations for group chats, every clause derived from a
    real field in `metrics`. Returned as strings because the group/analytics
    templates render each insight directly (x-text="insight")."""
    out = []
    vol = metrics.get('volume_ranked') or []
    total = metrics.get('total_messages', 0) or 1
    peak_day = metrics.get('peak_day')
    midnight = metrics.get('midnight_index', 0)

    # 1. Volume dominance + margin over the runner-up.
    if vol:
        top = vol[0]
        if len(vol) > 1:
            out.append(
                f"{top['name']} dominates the group with {top['pct']}% of all messages, "
                f"ahead of {vol[1]['name']} at {vol[1]['pct']}%."
            )
        else:
            out.append(f"{top['name']} sent {top['pct']}% of all messages.")

    # 2. Busiest day, with the peak hour if we have it.
    if peak_day and peak_day != "Unknown":
        ph = metrics.get('peak_hour_label')
        if ph:
            out.append(f"The group is most alive on {peak_day}s, peaking around {ph}.")
        else:
            out.append(f"{peak_day} is consistently the busiest day for the group.")

    # 3 & 4. Fastest and slowest responders.
    lat = metrics.get('latency_ranked_minutes') or []
    if lat:
        fastest = lat[0]
        out.append(
            f"{fastest['name']} is the quickest to reply, averaging "
            f"{_fmt_minutes(fastest['minutes'])} to respond."
        )
        if len(lat) > 1:
            slowest = lat[-1]
            out.append(
                f"{slowest['name']} is the slowest, taking about "
                f"{_fmt_minutes(slowest['minutes'])} on average to reply."
            )

    # 5. One-sided initiation.
    init = metrics.get('initiation_ranked') or []
    if len(init) > 1 and init[0]['pct'] >= 40:
        out.append(
            f"{init[0]['name']} breaks the silence most often, starting {init[0]['pct']}% "
            f"of conversations after a 6h+ gap."
        )

    # 6. Quietest member and their share.
    quiet = metrics.get('quietest_member')
    if quiet and len(vol) > 2:
        q_pct = round(quiet['count'] / total * 100, 1)
        out.append(
            f"{quiet['name']} is the quietest member, contributing just {q_pct}% "
            f"of the group's messages."
        )

    # 7. Late-night rhythm.
    if midnight and midnight > 25:
        out.append(
            f"Around {int(midnight)}% of messages land between 11pm and 4am — "
            f"this group keeps late hours."
        )

    # 8. Strongest emoji personality (lowest chars-per-emoji = most emoji-heavy).
    emoji = metrics.get('emoji_ratio_ranked') or []
    if len(out) < 6 and len(emoji) > 1:
        heavy = min(emoji, key=lambda e: e['ratio'])
        if heavy.get('top_emoji'):
            out.append(
                f"{heavy['name']} has the strongest emoji personality, leaning hardest "
                f"on {heavy['top_emoji']}."
            )

    return out[:6]


def generate_insight(metrics, chat_type):
    """Rules-based observation sentences from real computed numbers. Capped at 3."""
    if chat_type == 'group':
        return _group_insights(metrics)
    insights = []
    midnight = metrics.get('midnight_index', 0)
    if midnight > 30:
        insights.append(
            f"Over {int(midnight)}% of messages happen between 11pm and 4am — "
            f"this conversation has a strong late-night rhythm."
        )
    peak_day = metrics.get('peak_day') or (metrics.get('rhythm') or {}).get('peak_day')
    if peak_day and peak_day != "Unknown":
        insights.append(
            f"{peak_day} is consistently the busiest day, suggesting a regular weekly pattern."
        )
    if chat_type == '1v1':
        init_counts = metrics.get('initiation_counts', [0, 0])
        participants = metrics.get('participants', ['A', 'B'])
        init_total = sum(init_counts) + 1
        pct_0 = init_counts[0] / init_total
        if pct_0 > 0.65:
            insights.append(
                f"{participants[0]} starts the majority of conversations after silence — "
                f"a fairly one-sided initiation pattern."
            )
        elif pct_0 < 0.35:
            insights.append(
                f"{participants[1]} tends to re-open the conversation more often — "
                f"a fairly one-sided initiation pattern."
            )
        else:
            insights.append("Both participants initiate conversations about equally often.")
        streak = (metrics.get('rhythm') or {}).get('longest_streak_days', 0)
        if streak >= 7 and len(insights) < 3:
            insights.append(
                f"The longest active streak was {streak} consecutive days — "
                f"a period of consistent daily contact."
            )
    return insights[:3]


# Media classification. We track a per-type breakdown instead of a single count.
MEDIA_TYPES = ('images', 'videos', 'audio', 'stickers', 'gifs',
               'documents', 'locations', 'contacts', 'deleted')

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
             'Saturday', 'Sunday']

# A document attachment named like "report.pdf (file attached)" / "...omitted".
_DOC_EXT_RE = re.compile(r'\.(pdf|docx|xlsx|txt|zip)\b[^\n]*omitted', re.IGNORECASE)
# iOS attachment placeholder, e.g. "<attached: 0000-PHOTO-2021.jpg>".
_IOS_ATTACH_RE = re.compile(r'<attached:[^>]*>', re.IGNORECASE)


def _new_media_record():
    return {k: 0 for k in MEDIA_TYPES}


def classify_media(text):
    """Classify a message body into a media/deleted type, or None for a normal
    message. Specific omission strings are tested before the generic
    "<Media omitted>" fallback so videos/audio/etc. aren't all lumped as images.
    """
    t = text.lower()
    # Deleted messages carry no real content; attributed to their sender.
    if 'this message was deleted' in t or 'you deleted this message' in t:
        return 'deleted'
    # Specific types first.
    if 'video omitted' in t:
        return 'videos'
    if 'audio omitted' in t or 'voice message omitted' in t or 'ptt omitted' in t:
        return 'audio'
    if 'sticker omitted' in t:
        return 'stickers'
    if 'gif omitted' in t:
        return 'gifs'
    if 'contact card omitted' in t or '.vcf omitted' in t:
        return 'contacts'
    if 'document omitted' in t or _DOC_EXT_RE.search(t):
        return 'documents'
    if t.startswith('location:') or 'live location shared' in t:
        return 'locations'
    if 'image omitted' in t:
        return 'images'
    # Generic fallbacks last.
    if '<media omitted>' in t or _IOS_ATTACH_RE.search(text):
        return 'images'
    return None

# System / notification lines that must never be counted as participant messages.
# These usually have no "sender:" colon, but occasionally one slips through when
# the body itself contains a colon (e.g. a renamed subject), so we also test the
# captured sender field against this pattern.
SYSTEM_MSG_RE = re.compile(
    r'\b(?:left|added|removed|joined|'
    r'changed the subject|changed their phone number|changed the group|'
    r'created group|created this group|security code changed|changed to)\b',
    re.IGNORECASE
)

# Any line that begins with a date stamp. Used to recognise dated lines that did
# NOT match a sender pattern — those are system notifications, not continuations.
DATED_LINE_RE = re.compile(r'^\[?\d{1,2}/\d{1,2}/\d{2,4}[,.\s]')

# Unified header patterns. Date fields are captured separately so day/month order
# can be resolved across the whole file. Seconds and am/pm are optional, and
# spacing is flexible (newer exports use a narrow no-break space before am/pm).
HEADER_RE_ANDROID = re.compile(
    r'^(\d{1,2})/(\d{1,2})/(\d{2,4}),\s+'
    r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]m)?\s*-\s*([^:]+):\s(.*)$',
    re.IGNORECASE,
)
HEADER_RE_IOS = re.compile(
    r'^\[(\d{1,2})/(\d{1,2})/(\d{2,4}),\s+'
    r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]m)?\]\s*([^:]+):\s(.*)$',
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────
# CALL DETECTION
# ─────────────────────────────────────────────────────────────

# Invisible bidi marks WhatsApp prefixes onto call/media notification bodies.
_BIDI_RE = re.compile(r'[‎‏‪-‮]')

# A duration like "5:23" (m:ss) or "1:12:45" (h:mm:ss) inside a call line.
_CALL_DURATION_RE = re.compile(r'\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b')

# A dated line with NO "sender:" colon. Lets us recover sender-less call
# notifications that the header regexes skip. Group 8 is the trailing text.
CALL_LINE_RE = re.compile(
    r'^\[?(\d{1,2})/(\d{1,2})/(\d{2,4}),\s+'
    r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]m)?\]?\s*-?\s*(.*)$',
    re.IGNORECASE,
)


def _parse_call_duration(text):
    """First m:ss / h:mm:ss in `text` → total seconds, or None."""
    m = _CALL_DURATION_RE.search(text)
    if not m:
        return None
    hours = int(m.group(1)) if m.group(1) else 0
    return hours * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def parse_call(text, allow_called_verb):
    """Detect a WhatsApp call-log line.

    Returns {'call_type', 'outcome', 'duration_seconds', 'name', 'is_you'} or
    None. `name` is any caller embedded in the text ("...from Alice"); `is_you`
    flags the "You called" form. `allow_called_verb` enables the "<Name> called"
    / "You called" forms — used only for sender-less lines, so an ordinary
    message body like "Mike called" isn't misread as a call.
    """
    t = _BIDI_RE.sub('', text).strip()

    # Type-based form: "(Missed) Voice/Video call[, 5:23][ from Name]".
    m = re.match(
        r'^(missed\s+)?(voice|video)\s+call'
        r'(?:,?\s*((?:\d{1,2}:)?\d{1,2}:\d{2}))?'
        r'(?:\s+from\s+(.+?))?'
        r'\.?\s*$',
        t, re.IGNORECASE,
    )
    if m:
        missed = bool(m.group(1))
        call_type = 'video' if m.group(2).lower() == 'video' else 'voice'
        dur = None if missed else (_parse_call_duration(m.group(3)) if m.group(3) else None)
        name = m.group(4).strip() if m.group(4) else None
        outcome = 'answered' if dur is not None else 'missed'
        return {'call_type': call_type, 'outcome': outcome,
                'duration_seconds': dur, 'name': name, 'is_you': False}

    # Verb form: "<Name> called" / "You called" (optionally "...Tap to call back.").
    if allow_called_verb:
        m = re.match(
            r'^(.+?)\s+called\.?(?:\s*tap to call back\.?)?\s*$',
            t, re.IGNORECASE,
        )
        if m:
            raw = m.group(1).strip()
            is_you = raw.lower() == 'you'
            dur = _parse_call_duration(t)
            outcome = 'answered' if dur is not None else 'missed'
            return {'call_type': 'voice', 'outcome': outcome,
                    'duration_seconds': dur,
                    'name': None if is_you else raw, 'is_you': is_you}
    return None


# ─────────────────────────────────────────────────────────────
# PARSE WHATSAPP FILE
# ─────────────────────────────────────────────────────────────

def parse_whatsapp_file(content):
    lines = content.splitlines()

    media_breakdown = defaultdict(_new_media_record)
    entries = []          # raw header rows; timestamps resolved in a second pass
    f1_vals = []          # first date field across the file (day or month)
    f2_vals = []          # second date field across the file (month or day)
    current = None        # last entry, for multi-line continuation

    for raw in lines:
        # Normalise exotic whitespace (U+202F narrow no-break, U+00A0 no-break).
        line = raw.replace(' ', ' ').replace(' ', ' ').strip()
        if not line:
            continue
        if line.startswith('Messages and calls are end-to-end encrypted'):
            continue

        m = HEADER_RE_ANDROID.match(line) or HEADER_RE_IOS.match(line)
        if not m:
            # Sender-less call notifications ("Alice called", "You called",
            # "Missed voice call") have no "sender:" colon, so the header regexes
            # skip them. Recover them here before the dated-line discard.
            cm = CALL_LINE_RE.match(line)
            if cm:
                call_info = parse_call(cm.group(8), allow_called_verb=True)
                if call_info:
                    if call_info.get('is_you'):
                        call_info['caller'] = '__YOU__'   # resolved after parsing
                    else:
                        call_info['caller'] = call_info.get('name')  # may be None
                    entries.append({
                        'f1': int(cm.group(1)), 'f2': int(cm.group(2)),
                        'year': int(cm.group(3)), 'hour': int(cm.group(4)),
                        'minute': int(cm.group(5)),
                        'second': int(cm.group(6)) if cm.group(6) else 0,
                        'ampm': cm.group(7).lower() if cm.group(7) else None,
                        'sender': None, 'text': '', 'media_type': None,
                        'call': call_info,
                    })
                    f1_vals.append(int(cm.group(1)))
                    f2_vals.append(int(cm.group(2)))
                    current = None
                    continue
            # A dated line with no "sender:" is a system notification
            # (e.g. "Alice left", "Bob added Carol") — skip it, and don't let
            # subsequent lines attach to a stale message.
            if DATED_LINE_RE.match(line):
                current = None
                continue
            # Otherwise it's a continuation of the previous message.
            if current is not None:
                current['text'] += '\n' + line
            continue

        f1, f2, year, hour, minute, second, ampm, sender, text = m.groups()
        sender = sender.strip()
        text = text.strip()

        # Call-log line carrying a sender (e.g. "Alice: Missed voice call",
        # "Bob: Voice call, 5:23"). Capture it as a call BEFORE the system-message
        # filter / media check, so it isn't discarded or miscounted as a message.
        # Only the type-based forms appear here; the caller is the sender.
        call_info = parse_call(text, allow_called_verb=False)
        if call_info:
            call_info['caller'] = sender
            entries.append({
                'f1': int(f1), 'f2': int(f2), 'year': int(year),
                'hour': int(hour), 'minute': int(minute),
                'second': int(second) if second else 0,
                'ampm': ampm.lower() if ampm else None,
                'sender': sender, 'text': '', 'media_type': None,
                'call': call_info,
            })
            f1_vals.append(int(f1))
            f2_vals.append(int(f2))
            current = None
            continue

        # System message that carried a colon and matched the header pattern.
        if SYSTEM_MSG_RE.search(sender):
            current = None
            continue

        # Media/deleted lines are kept as entries too (tagged with media_type) so
        # their timestamps get resolved in the second pass — that's what lets media
        # be date-filtered. We drop their placeholder text (metadata only).
        mtype = classify_media(text)
        entry = {
            'f1': int(f1), 'f2': int(f2), 'year': int(year),
            'hour': int(hour), 'minute': int(minute),
            'second': int(second) if second else 0,
            'ampm': ampm.lower() if ampm else None,
            'sender': sender,
            'text': '' if mtype else text,
            'media_type': mtype,
        }
        entries.append(entry)
        f1_vals.append(entry['f1'])
        f2_vals.append(entry['f2'])
        # A media entry never accepts continuation lines; a real message does.
        current = None if mtype else entry

    # Resolve day-first (dd/mm) vs month-first (mm/dd) for the whole file: if any
    # first field exceeds 12 it must be a day; if any second field does, the first
    # is the month. Default to day-first (WhatsApp's most common locale layout).
    if any(v > 12 for v in f1_vals):
        day_first = True
    elif any(v > 12 for v in f2_vals):
        day_first = False
    else:
        day_first = True

    messages = []
    media_events = []
    call_events_raw = []
    participants = set()
    for e in entries:
        if day_first:
            day, month = e['f1'], e['f2']
        else:
            month, day = e['f1'], e['f2']

        year = e['year']
        if year < 100:
            year += 2000

        hour = e['hour']
        if e['ampm'] == 'pm' and hour != 12:
            hour += 12
        elif e['ampm'] == 'am' and hour == 12:
            hour = 0

        try:
            timestamp = datetime(year, month, day, hour, e['minute'], e['second'])
        except ValueError:
            continue

        call = e.get('call')
        if call:
            call_events_raw.append({'call': call, 'timestamp': timestamp})
            continue

        mtype = e.get('media_type')
        if mtype:
            media_breakdown[e['sender']][mtype] += 1
            media_events.append({
                'sender': e['sender'],
                'timestamp': timestamp,
                'type': mtype,
            })
            continue

        msg = {'timestamp': timestamp, 'sender': e['sender'], 'text': e['text']}
        messages.append(msg)
        participants.add(e['sender'])

    # "You called" lines have no sender; attribute them to the most active
    # participant (the export owner is almost always the busiest sender).
    top_sender = (
        Counter(m['sender'] for m in messages).most_common(1)[0][0]
        if messages else None
    )
    call_events = []
    for ev in call_events_raw:
        c = ev['call']
        ts = ev['timestamp']
        caller = c.get('caller')
        if caller == '__YOU__':
            caller = top_sender
        call_events.append({
            'caller': caller,
            'call_type': c['call_type'],
            'outcome': c['outcome'],
            'duration_seconds': c['duration_seconds'],
            'timestamp': ts.isoformat(),
            'day_of_week': DAY_NAMES[ts.weekday()],
            'hour': ts.hour,
        })

    return (
        messages,
        participants,
        {k: dict(v) for k, v in media_breakdown.items()},
        media_events,
        call_events,
    )


# Historical alias — the parser was renamed from parse_whatsapp_chat.
parse_whatsapp_chat = parse_whatsapp_file


def media_breakdown_from_events(events):
    """Aggregate a list of media event dicts ({'sender','timestamp','type'}) back
    into the {sender: {type: count}} shape that the compute_* functions expect.
    Used to rebuild the breakdown for a filtered date range."""
    out = defaultdict(_new_media_record)
    for ev in events:
        if ev.get('type') in MEDIA_TYPES:
            out[ev['sender']][ev['type']] += 1
    return {k: dict(v) for k, v in out.items()}


def _person_media(media_breakdown, name):
    """A full per-person media record (all types present, missing → 0)."""
    rec = media_breakdown.get(name) or {}
    return {k: rec.get(k, 0) for k in MEDIA_TYPES}


def _total_media(rec):
    """Sum of media items, excluding deleted messages (not real media)."""
    return sum(v for k, v in rec.items() if k != 'deleted')


# ─────────────────────────────────────────────────────────────
# MEMORABLE MOMENTS (Phase C3)
# ─────────────────────────────────────────────────────────────

# strftime has no portable "no leading zero" day token: glibc uses %-d, the
# Windows CRT uses %#d. Pick the right one once at import time.
_DAY_FMT = '%#d %b %Y' if sys.platform.startswith('win') else '%-d %b %Y'


def _day_label(dt):
    """A datetime → '14 Mar 2023' style label."""
    return dt.strftime(_DAY_FMT)


def _mm_first_last(messages):
    first, last = messages[0], messages[-1]
    return (
        {'sender': first['sender'], 'text': first['text'],
         'date_label': _day_label(first['timestamp'])},
        {'sender': last['sender'], 'text': last['text'],
         'date_label': _day_label(last['timestamp'])},
    )


def _mm_longest_message(messages):
    # By word count; ties resolve to the earlier message. `max` keeps the first
    # maximal element, and `messages` is chronological, so the tie-break is free.
    longest = max(messages, key=lambda m: len(m['text'].split()))
    return {
        'sender': longest['sender'],
        'word_count': len(longest['text'].split()),
        'snippet': longest['text'][:120],
        'date_label': _day_label(longest['timestamp']),
    }


def _mm_days(messages):
    """calendar date → list of that day's messages (insertion = chronological)."""
    day_msgs = defaultdict(list)
    for m in messages:
        day_msgs[m['timestamp'].date()].append(m)
    return day_msgs


def _mm_biggest_day(day_msgs):
    # Most messages in a day; ties resolve to the earlier date.
    best = max(day_msgs, key=lambda d: (len(day_msgs[d]), -d.toordinal()))
    counts = Counter(m['sender'] for m in day_msgs[best])
    leader, leader_count = counts.most_common(1)[0]
    return {
        'date_label': _day_label(day_msgs[best][0]['timestamp']),
        'msg_count': len(day_msgs[best]),
        'leader': leader,
        'leader_count': leader_count,
    }


def _mm_longest_streak(day_msgs):
    days = sorted(day_msgs.keys())
    best_len, best_start, best_end = 1, days[0], days[0]
    cur_len, cur_start = 1, days[0]
    for i in range(1, len(days)):
        if (days[i] - days[i - 1]).days == 1:
            cur_len += 1
        else:
            cur_len, cur_start = 1, days[i]
        if cur_len > best_len:
            best_len, best_start, best_end = cur_len, cur_start, days[i]
    return {
        'days': best_len,
        'start_label': best_start.strftime(_DAY_FMT),
        'end_label': best_end.strftime(_DAY_FMT),
    }


def _mm_longest_silence(messages):
    if len(messages) < 2:
        return None
    max_gap, idx = -1.0, 1
    for i in range(1, len(messages)):
        gap = (messages[i]['timestamp'] - messages[i - 1]['timestamp']).total_seconds()
        if gap > max_gap:
            max_gap, idx = gap, i
    return {
        'gap_hours': round(max_gap / 3600, 1),
        'broken_by': messages[idx]['sender'],
        'date_label': _day_label(messages[idx]['timestamp']),
    }


def _mm_most_emoji_day(messages):
    day_emojis = defaultdict(list)
    for m in messages:
        chars = extract_emojis(m['text'])
        if chars:
            day_emojis[m['timestamp'].date()].extend(chars)
    if not day_emojis:
        return None
    # Highest total; ties resolve to the earlier date.
    best = max(day_emojis, key=lambda d: (len(day_emojis[d]), -d.toordinal()))
    top_emoji = Counter(day_emojis[best]).most_common(1)[0][0]
    return {
        'date_label': best.strftime(_DAY_FMT),
        'emoji_count': len(day_emojis[best]),
        'top_emoji': top_emoji,
    }


def _mm_fastest_reply(messages):
    best = None
    for i in range(len(messages) - 1):
        cur, nxt = messages[i], messages[i + 1]
        if nxt['sender'] == cur['sender']:
            continue
        gap = (nxt['timestamp'] - cur['timestamp']).total_seconds()
        if 5 <= gap <= 3600 and (best is None or gap < best['seconds']):
            best = {
                'sender': nxt['sender'],
                'seconds': int(gap),
                'to_whom': cur['sender'],
                'date_label': _day_label(nxt['timestamp']),
            }
    return best


def compute_memorable_moments(messages, participants):
    """Highlight reel for a 1v1 chat. `messages` is text-only and is sorted
    defensively here so the result is correct regardless of caller order."""
    if not messages:
        return None
    messages = sorted(messages, key=lambda m: m['timestamp'])
    first, last = _mm_first_last(messages)
    day_msgs = _mm_days(messages)
    return {
        'first_message': first,
        'last_message': last,
        'longest_message': _mm_longest_message(messages),
        'most_emoji_day': _mm_most_emoji_day(messages),
        'biggest_day': _mm_biggest_day(day_msgs),
        'longest_streak': _mm_longest_streak(day_msgs),
        'longest_silence': _mm_longest_silence(messages),
        'fastest_reply': _mm_fastest_reply(messages),
    }


def compute_group_memorable_moments(messages):
    """Condensed highlight reel for a group chat — no per-sender reply timing or
    emoji-day noise."""
    if not messages:
        return None
    messages = sorted(messages, key=lambda m: m['timestamp'])
    first, last = _mm_first_last(messages)
    day_msgs = _mm_days(messages)
    return {
        'first_message': first,
        'last_message': last,
        'biggest_day': _mm_biggest_day(day_msgs),
        'longest_streak': _mm_longest_streak(day_msgs),
        'longest_silence': _mm_longest_silence(messages),
    }


# ─────────────────────────────────────────────────────────────
# CALL STATISTICS
# ─────────────────────────────────────────────────────────────

def _max_consecutive_days(dates):
    """Longest run of consecutive calendar days in a set/iterable of dates."""
    if not dates:
        return 0
    days = sorted(set(dates))
    best = run = 1
    for prev, cur in zip(days, days[1:]):
        if (cur - prev).days == 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def _empty_call_person():
    return {
        'initiated': 0, 'missed_received': 0, 'voice': 0, 'video': 0,
        'total_duration_seconds': 0, 'avg_duration_seconds': 0.0,
        'longest_call_seconds': 0,
    }


def compute_call_stats(call_events, participants):
    """Aggregate call metrics from a list of call_event dicts. When there are no
    calls, returns the dict with has_data=False and zeros so the UI hides the
    section cleanly."""
    participants = list(participants or [])
    stats = {
        'total_calls': 0, 'total_voice_calls': 0, 'total_video_calls': 0,
        'missed_calls': 0, 'answered_calls': 0, 'answer_rate': 0.0,
        'calls_by_person': {},
        'calls_by_day': {d: 0 for d in DAY_NAMES},
        'calls_by_hour': {h: 0 for h in range(24)},
        'most_active_call_day': None,
        'most_active_call_hour': None,
        'most_active_call_hour_label': None,
        'avg_call_duration_seconds': 0.0,
        'longest_call': None,
        'who_calls_more': None,
        'call_streak': 0,
        'has_data': False,
    }
    if not call_events:
        return stats

    by_person = {p: _empty_call_person() for p in participants}
    answered_durations = []
    person_durations = defaultdict(list)
    longest = None
    call_dates = set()

    for ev in call_events:
        caller = ev.get('caller')
        ctype = ev.get('call_type')
        outcome = ev.get('outcome')
        dur = ev.get('duration_seconds')
        day = ev.get('day_of_week')
        hour = ev.get('hour')

        stats['total_calls'] += 1
        if ctype == 'video':
            stats['total_video_calls'] += 1
        else:
            stats['total_voice_calls'] += 1

        if outcome == 'answered':
            stats['answered_calls'] += 1
            if isinstance(dur, int):
                answered_durations.append(dur)
        else:
            stats['missed_calls'] += 1

        if day in stats['calls_by_day']:
            stats['calls_by_day'][day] += 1
        if isinstance(hour, int) and 0 <= hour <= 23:
            stats['calls_by_hour'][hour] += 1

        if caller and caller not in by_person:
            by_person[caller] = _empty_call_person()
        if caller in by_person:
            rec = by_person[caller]
            rec['initiated'] += 1
            rec['video' if ctype == 'video' else 'voice'] += 1
            if outcome == 'answered' and isinstance(dur, int):
                rec['total_duration_seconds'] += dur
                rec['longest_call_seconds'] = max(rec['longest_call_seconds'], dur)
                person_durations[caller].append(dur)

        # The other participant(s) are on the receiving end of a missed call.
        if outcome == 'missed':
            for p in by_person:
                if p != caller:
                    by_person[p]['missed_received'] += 1

        if outcome == 'answered' and isinstance(dur, int):
            if longest is None or dur > longest['duration_seconds']:
                longest = {
                    'duration_seconds': dur,
                    'caller': caller,
                    'date_label': _day_label(datetime.fromisoformat(ev['timestamp'])),
                    'call_type': ctype,
                }

        try:
            call_dates.add(datetime.fromisoformat(ev['timestamp']).date())
        except (ValueError, TypeError, KeyError):
            pass

    for p, rec in by_person.items():
        durs = person_durations.get(p, [])
        rec['avg_duration_seconds'] = round(statistics.mean(durs), 1) if durs else 0.0

    total = stats['total_calls']
    stats['answer_rate'] = round(stats['answered_calls'] / total, 3) if total else 0.0
    stats['avg_call_duration_seconds'] = (
        round(statistics.mean(answered_durations), 1) if answered_durations else 0.0
    )
    stats['calls_by_person'] = by_person

    stats['most_active_call_day'] = max(DAY_NAMES, key=lambda d: stats['calls_by_day'][d])
    busiest_hour = max(range(24), key=lambda h: stats['calls_by_hour'][h])
    stats['most_active_call_hour'] = busiest_hour
    stats['most_active_call_hour_label'] = _hour_label(busiest_hour)

    initiators = {p: rec['initiated'] for p, rec in by_person.items()}
    if initiators and max(initiators.values()) > 0:
        stats['who_calls_more'] = max(initiators, key=lambda p: initiators[p])

    stats['longest_call'] = longest
    stats['call_streak'] = _max_consecutive_days(call_dates)
    stats['has_data'] = True
    return stats


# ─────────────────────────────────────────────────────────────
# METRICS DISPATCHER
# ─────────────────────────────────────────────────────────────

def compute_metrics(messages, participants, chat_type, media_breakdown=None,
                    call_events=None):
    if media_breakdown is None:
        media_breakdown = {}
    # Deterministic order: most active participant first, name as tie-breaker.
    # `participants` is a set, so list(set) order is non-deterministic and would
    # swap "you"/"them" between identical uploads.
    sender_counts = Counter(m['sender'] for m in messages)
    participants_list = sorted(
        participants, key=lambda p: (-sender_counts.get(p, 0), p)
    )
    if len(participants_list) < 2:
        return None
    if chat_type == '1v1' and len(participants_list) == 2:
        return compute_1to1_metrics(messages, participants_list, media_breakdown,
                                    call_events)
    return compute_group_metrics(messages, participants_list, media_breakdown,
                                 call_events)


# ─────────────────────────────────────────────────────────────
# 1V1 METRICS (ENHANCED VERSION)
# ─────────────────────────────────────────────────────────────

def compute_1to1_metrics(messages, participants, media_breakdown, call_events=None):
    pA, pB = participants[0], participants[1]
    mb_A = _person_media(media_breakdown, pA)
    mb_B = _person_media(media_breakdown, pB)

    msgs_A = [m for m in messages if m['sender'] == pA]
    msgs_B = [m for m in messages if m['sender'] == pB]

    total_msgs = len(messages)
    chars_A = sum(len(m['text']) for m in msgs_A)
    chars_B = sum(len(m['text']) for m in msgs_B)

    def initiation_rate(sender):
        initiates = 0
        last_ts = None
        for m in messages:
            if last_ts and (m['timestamp'] - last_ts).total_seconds() > 6 * 3600:
                if m['sender'] == sender:
                    initiates += 1
            last_ts = m['timestamp']
        return initiates

    init_A = initiation_rate(pA)
    init_B = initiation_rate(pB)

    def response_latency(from_sender, to_sender):
        latencies = []
        last_from_ts = None
        for m in messages:
            if m['sender'] == from_sender:
                last_from_ts = m['timestamp']
            elif m['sender'] == to_sender and last_from_ts:
                delay = (m['timestamp'] - last_from_ts).total_seconds()
                if 0 < delay < 86400:
                    latencies.append(delay)
                last_from_ts = None
        return statistics.mean(latencies) if latencies else None

    latency_A_to_B = response_latency(pA, pB)
    latency_B_to_A = response_latency(pB, pA)

    emoji_A = sum(count_emojis(m['text']) for m in msgs_A)
    emoji_B = sum(count_emojis(m['text']) for m in msgs_B)
    text_len_A = chars_A - emoji_A
    text_len_B = chars_B - emoji_B

    def midnight_ratio(msgs):
        if not msgs:
            return 0
        return sum(1 for m in msgs if m['timestamp'].hour >= 23 or m['timestamp'].hour < 4) / len(msgs) * 100

    mid_idx = len(messages) // 2
    positive_words = {'love', 'nice', 'good', 'great', 'happy', 'amazing', 'awesome', 'bless', 'proud'}
    negative_words = {'hate', 'bad', 'sad', 'angry', 'annoying', 'awful', 'terrible', 'sorry', 'hurt'}

    def avg_sentiment(msgs):
        pos = neg = 0
        for m in msgs:
            words = set(m['text'].lower().split())
            pos += len(words & positive_words)
            neg += len(words & negative_words)
        return (pos - neg) / (pos + neg + 1)

    sentiment_drift = round(avg_sentiment(messages[mid_idx:]) - avg_sentiment(messages[:mid_idx]), 2)

    last_10pct = max(1, int(len(messages) * 0.1))
    last_msgs = messages[-last_10pct:]

    def latency_in_segment(msgs, from_sender, to_sender):
        lat = []
        last_from = None
        for m in msgs:
            if m['sender'] == from_sender:
                last_from = m['timestamp']
            elif m['sender'] == to_sender and last_from:
                lat.append((m['timestamp'] - last_from).total_seconds())
                last_from = None
        return statistics.mean(lat) if lat else None

    recent_lat_A_to_B = latency_in_segment(last_msgs, pA, pB)
    if latency_A_to_B is None or recent_lat_A_to_B is None:
        ghosting_risk = "Low"
    elif recent_lat_A_to_B > latency_A_to_B * 1.5:
        ghosting_risk = "High"
    else:
        ghosting_risk = "Low"

    double_text_count = sum(
        1 for i in range(len(messages) - 1)
        if messages[i]['sender'] == messages[i + 1]['sender']
        and (messages[i + 1]['timestamp'] - messages[i]['timestamp']).total_seconds() < 300
    )

    def top_emojis(msgs, n=5):
        c = Counter()
        for m in msgs:
            c.update(extract_emojis(m['text']))
        return c.most_common(n)

    hourly_A = [0] * 24
    hourly_B = [0] * 24
    for m in msgs_A:
        hourly_A[m['timestamp'].hour] += 1
    for m in msgs_B:
        hourly_B[m['timestamp'].hour] += 1

    hourly_total = [hourly_A[i] + hourly_B[i] for i in range(24)]

    # Health score
    init_balance = 1 - abs(init_A - init_B) / (init_A + init_B + 1)
    if latency_A_to_B is not None and latency_B_to_A is not None:
        max_lat = max(latency_A_to_B, latency_B_to_A)
        latency_balance = 1 - min(1, abs(latency_A_to_B - latency_B_to_A) / (max_lat + 1))
    else:
        latency_balance = 0.5
    volume_balance = 1 - abs(len(msgs_A) - len(msgs_B)) / (total_msgs + 1)
    sentiment_score = (avg_sentiment(messages[mid_idx:]) + 1) / 2
    health = int(min(100, max(0,
        (init_balance * 0.25 + latency_balance * 0.25 + volume_balance * 0.25 + sentiment_score * 0.25) * 100
    )))

    if health >= 80:
        verdict = "Highly Synchronized"
    elif health >= 60:
        verdict = "Steady & Warm"
    elif health >= 40:
        verdict = "Needs Attention"
    else:
        verdict = "Distant Vibes"

    lat_display = f"{latency_B_to_A / 60:.1f} min" if latency_B_to_A is not None else "an unknown time"
    summary = (
        f"{pA} and {pB} display a {verdict.lower()} dynamic. "
        f"{pA} initiates {init_A / (init_A + init_B + 1) * 100:.0f}% of conversations, "
        f"while {pB} replies in {lat_display} on average. "
        f"Your late-night activity occupies {midnight_ratio(messages):.0f}% of chats. "
        f"Sentiment has {'improved' if sentiment_drift > 0 else 'declined'} over time."
    )

    # Textual DNA — `media` is the per-person total of real media (deleted excluded).
    dna_A = _textual_dna(msgs_A)
    dna_A['media'] = _total_media(mb_A)
    dna_B = _textual_dna(msgs_B)
    dna_B['media'] = _total_media(mb_B)

    # Conversation Rhythm
    rhythm = _conversation_rhythm(messages)

    # Sync Snapshot extras
    span_days_count = max(
        (messages[-1]['timestamp'].date() - messages[0]['timestamp'].date()).days, 1
    ) if messages else 1
    avg_msgs_per_day = round(total_msgs / span_days_count, 1)
    month_counter = Counter(m['timestamp'].strftime('%B %Y') for m in messages)
    most_active_month = month_counter.most_common(1)[0][0] if month_counter else ''
    dominant_vol = max(len(msgs_A), len(msgs_B)) / (total_msgs + 1)
    if dominant_vol > 0.65:
        dominant = pA if len(msgs_A) > len(msgs_B) else pB
        response_balance_text = f"{dominant} tends to message more overall"
    else:
        response_balance_text = "Replies are fairly even"

    # Power Dynamics: initiation % for balance bar
    init_total_safe = init_A + init_B + 1
    initiation_pct = [round(init_A / init_total_safe * 100, 1), round(init_B / init_total_safe * 100, 1)]

    # ===== ENHANCED METRICS CALCULATIONS =====
    word_battle = compute_word_battle(msgs_A, msgs_B)
    word_histogram = compute_word_histogram(msgs_A, msgs_B)
    question_ratio = compute_question_ratio(msgs_A, msgs_B)
    abbrev_density = compute_abbrev_density(msgs_A, msgs_B)
    sentiment_volatility = compute_sentiment_volatility(messages)
    positivity_ratio = compute_positivity_ratio(messages)
    sentiment_over_time = compute_sentiment_over_time(messages)
    burstiness_score = compute_burstiness_score(messages)
    predictability_score = compute_predictability_score(messages)
    best_time_pA = compute_best_time_to_message(msgs_A)
    best_time_pB = compute_best_time_to_message(msgs_B)
    best_time_to_message = [best_time_pA, best_time_pB]
    turn_equality = compute_turn_equality(messages, participants)
    peak_hour_text = compute_peak_hour_text(hourly_total)
    best_day = compute_best_day_text(rhythm)

    # Health score as a structured breakdown (each component 0-100).
    # `health` (computed above) is the headline figure; the four sub-scores
    # explain it. predictability_score is reused as the consistency signal.
    def _clamp_pct(x):
        return int(round(min(100, max(0, x))))

    health_score = {
        'overall': health,
        'engagement': _clamp_pct(latency_balance * 100),
        'balance': _clamp_pct(((init_balance + volume_balance) / 2) * 100),
        'sentiment': _clamp_pct(sentiment_score * 100),
        'consistency': _clamp_pct(predictability_score),
    }

    if sentiment_drift > 0.05:
        sentiment_drift_text = f"Positive drift of +{sentiment_drift:.2f} — tone has improved over time. 🎉"
    elif sentiment_drift < -0.05:
        sentiment_drift_text = f"Negative drift of {sentiment_drift:.2f} — tone has declined over time. 😟"
    else:
        sentiment_drift_text = "Tone has remained broadly stable throughout the conversation. 📊"

    # ── Media breakdown (Phase C2) ──
    media_breakdown_out = {pA: mb_A, pB: mb_B}
    voice_note_initiator = pA if mb_A['audio'] >= mb_B['audio'] else pB
    deleted_messages = {pA: mb_A['deleted'], pB: mb_B['deleted']}
    total_media = _total_media(mb_A) + _total_media(mb_B)

    # ── Conversation sessions (Phase C1) ──
    sessions = compute_sessions(messages)
    sessions_total = len(sessions)
    session_initiations = {pA: 0, pB: 0}
    session_endings = {pA: 0, pB: 0}
    for s in sessions:
        if s['initiator'] in session_initiations:
            session_initiations[s['initiator']] += 1
        if s['ender'] in session_endings:
            session_endings[s['ender']] += 1
    avg_session_length_msgs = (
        round(statistics.mean([s['msg_count'] for s in sessions]), 1) if sessions else 0
    )
    avg_session_duration_minutes = (
        round(statistics.mean([s['duration_minutes'] for s in sessions]), 1) if sessions else 0
    )

    # Inter-session silences: gap between one session's end and the next's start.
    # Reviver = whoever re-opens after a >24h silence (subset of session starts).
    silence_gaps_hours = []
    reviver_counts = Counter()
    for prev_s, s in zip(sessions, sessions[1:]):
        gap_h = (s['start_dt'] - prev_s['end_dt']).total_seconds() / 3600
        silence_gaps_hours.append(round(min(gap_h, 168), 1))  # cap at 1 week for the histogram
        if gap_h > 24:
            reviver_counts[s['initiator']] += 1
    if reviver_counts:
        top_name, top_count = reviver_counts.most_common(1)[0]
        dead_chat_reviver = {'name': top_name, 'count': top_count}
    else:
        dead_chat_reviver = {'name': None, 'count': 0}

    result = {
        'mode': '1v1',
        'participants': [pA, pB],
        
        # Basic metrics
        'total_messages': total_msgs,
        'message_counts': [len(msgs_A), len(msgs_B)],
        'char_counts': [chars_A, chars_B],
        'avg_msgs_per_day': avg_msgs_per_day,
        'most_active_month': most_active_month,
        'response_balance_text': response_balance_text,
        
        # Power dynamics
        'initiation_counts': [init_A, init_B],
        'initiation_pct': initiation_pct,
        
        # Response latency
        'latency_seconds': [latency_A_to_B, latency_B_to_A],
        'latency_minutes': [
            round(latency_A_to_B / 60, 1) if latency_A_to_B is not None else None,
            round(latency_B_to_A / 60, 1) if latency_B_to_A is not None else None,
        ],
        
        # Textual DNA
        'textual_dna': [dna_A, dna_B],
        'text_to_emoji_ratio': [text_len_A / (emoji_A + 1), text_len_B / (emoji_B + 1)],

        # Media breakdown (Phase C2)
        'media_breakdown': media_breakdown_out,
        'voice_note_initiator': voice_note_initiator,
        'deleted_messages': deleted_messages,
        'total_media': total_media,
        
        # Word Battle
        'word_battle': word_battle,
        'word_histogram': word_histogram,
        'question_ratio': question_ratio,
        'abbrev_density': abbrev_density,
        
        # Emoji
        'top_emojis_A': top_emojis(msgs_A),
        'top_emojis_B': top_emojis(msgs_B),
        
        # Temporal
        'hourly_A': hourly_A,
        'hourly_B': hourly_B,
        'rhythm': rhythm,
        'peak_day': rhythm.get('peak_day'),
        'peak_hour_text': peak_hour_text,
        'best_day': best_day,
        'midnight_index': midnight_ratio(messages),
        'burstiness_score': burstiness_score,
        'predictability_score': predictability_score,
        'best_time_to_message': best_time_to_message,
        'turn_equality': turn_equality,
        
        # Emotional
        'sentiment_drift': sentiment_drift,
        'sentiment_drift_text': sentiment_drift_text,
        'sentiment_volatility': round(sentiment_volatility, 3),
        'positivity_ratio': positivity_ratio,
        'sentiment_over_time': sentiment_over_time,
        
        # Anomalies
        'ghosting_risk': ghosting_risk,
        'double_text_count': double_text_count,

        # Conversation sessions (Phase C1)
        'sessions_total': sessions_total,
        'session_initiations': session_initiations,
        'session_endings': session_endings,
        'dead_chat_reviver': dead_chat_reviver,
        'avg_session_length_msgs': avg_session_length_msgs,
        'avg_session_duration_minutes': avg_session_duration_minutes,
        'silence_gaps_hours': silence_gaps_hours,

        # Health
        'health_score': health_score,
        'verdict': verdict,

        # Summary & Insights
        'summary': summary,
    }

    # Memorable moments (Phase C3) — `messages` here is already text-only.
    result['memorable_moments'] = compute_memorable_moments(messages, participants)

    # Call analysis — empty/zeroed (has_data=False) when the export has no calls.
    result['call_stats'] = compute_call_stats(call_events or [], participants)

    # Insights must be generated after `result` exists — generate_insight reads
    # back fields like initiation_counts, peak_day, rhythm and midnight_index.
    result['insights'] = generate_insight(result, '1v1')

    return result


# ─────────────────────────────────────────────────────────────
# GROUP METRICS (KEEP YOUR EXISTING IMPLEMENTATION)
# ─────────────────────────────────────────────────────────────

# Legacy alias — kept so existing call sites stay readable; delegates to the
# single source of truth above.
_count_emojis = count_emojis


def _hour_label(h):
    """0–23 → '9 PM' style label."""
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def compute_group_metrics(messages, participants, media_breakdown, call_events=None):
    """Per-participant rankings + group-wide pulse for multi-person chats.

    Field shapes here are dictated by dashboard_group.html and analytics.html
    (the templates are the contract), not by raw convenience:
      * rankings carry `pct`/`minutes`/`shift` as the templates read them,
      * group_pulse is a list of [label, count] pairs (the area chart maps p[0]/p[1]),
      * media_shared is a {name: count} dict (the template does Object.entries),
      * media_breakdown is {name: {images, videos, audio, ...}} (Phase C2),
      * insights is a list of plain strings.
    """
    total = len(messages)
    msgs_by = {p: [m for m in messages if m['sender'] == p] for p in participants}
    counts = {p: len(v) for p, v in msgs_by.items()}
    # `participants` already arrives volume-sorted from compute_metrics; re-sort
    # defensively so every ranking below is deterministic on identical uploads.
    ranked_names = sorted(participants, key=lambda p: (-counts[p], p))

    # ── Volume ──
    volume_ranked = [
        {'name': p, 'count': counts[p],
         'pct': round(counts[p] / total * 100, 1) if total else 0}
        for p in ranked_names
    ]

    # ── Initiation: first message after a 6h+ silence (matches the UI's label) ──
    GAP_SECONDS = 6 * 3600
    init_counts = Counter()
    last_ts = None
    for m in messages:
        if last_ts is not None and (m['timestamp'] - last_ts).total_seconds() > GAP_SECONDS:
            init_counts[m['sender']] += 1
        last_ts = m['timestamp']
    init_total = sum(init_counts.values())
    initiation_ranked = sorted(
        [
            {'name': p, 'count': init_counts[p],
             'pct': round(init_counts[p] / init_total * 100, 1) if init_total else 0}
            for p in participants if init_counts[p] > 0
        ],
        key=lambda x: (-x['count'], x['name']),
    )

    # ── Response latency: reply to the previous (different) sender, ≤24h, ≥3 to qualify ──
    latencies = defaultdict(list)
    for i in range(1, len(messages)):
        prev, cur = messages[i - 1], messages[i]
        if cur['sender'] != prev['sender']:
            delay = (cur['timestamp'] - prev['timestamp']).total_seconds()
            if 0 < delay < 86400:
                latencies[cur['sender']].append(delay)
    latency_ranked_minutes = sorted(
        [
            {'name': p, 'minutes': round(statistics.mean(v) / 60, 1)}
            for p, v in latencies.items() if len(v) >= 3
        ],
        key=lambda x: x['minutes'],  # fastest first
    )

    # ── Activity shift: final 7-day window vs the 7 days before it ──
    activity_shift_ranked = []
    if messages:
        end = messages[-1]['timestamp']
        wk1_start = end - timedelta(days=7)
        wk2_start = end - timedelta(days=14)
        this_wk, last_wk = Counter(), Counter()
        for m in messages:
            ts = m['timestamp']
            if ts > wk1_start:
                this_wk[m['sender']] += 1
            elif ts > wk2_start:
                last_wk[m['sender']] += 1
        activity_shift_ranked = sorted(
            [
                {'name': p, 'this_week': this_wk[p], 'last_week': last_wk[p],
                 'shift': this_wk[p] - last_wk[p]}
                for p in participants if this_wk[p] or last_wk[p]
            ],
            key=lambda x: (-x['this_week'], x['name']),
        )

    # ── Double-texts: same sender twice within 5 minutes ──
    dbl = Counter()
    for i in range(1, len(messages)):
        prev, cur = messages[i - 1], messages[i]
        if cur['sender'] == prev['sender'] and \
                (cur['timestamp'] - prev['timestamp']).total_seconds() < 300:
            dbl[cur['sender']] += 1
    double_text_ranked = sorted(
        [{'name': p, 'count': dbl[p]} for p in participants],
        key=lambda x: (-x['count'], x['name']),
    )

    # ── Emoji ratio: text chars per emoji (higher = more text-heavy, per the UI) ──
    emoji_ratio_ranked = []
    for p in participants:
        emoji_total = sum(_count_emojis(m['text']) for m in msgs_by[p])
        chars = sum(len(m['text']) for m in msgs_by[p])
        c = Counter()
        for m in msgs_by[p]:
            c.update(extract_emojis(m['text']))
        emoji_ratio_ranked.append({
            'name': p,
            'ratio': round((chars - emoji_total) / (emoji_total + 1), 1),
            'top_emoji': c.most_common(1)[0][0] if c else '',
        })
    emoji_ratio_ranked.sort(key=lambda x: (-x['ratio'], x['name']))

    # ── Media breakdown per participant (Phase C2) ──
    media_breakdown_out = {p: _person_media(media_breakdown, p) for p in ranked_names}

    # ── Textual DNA (reuse the 1v1 helper; add name + media for the table/sparklines) ──
    textual_dna_ranked = []
    for p in ranked_names:
        dna = _textual_dna(msgs_by[p])
        dna['name'] = p
        dna['media'] = _total_media(media_breakdown_out[p])
        textual_dna_ranked.append(dna)

    # ── Group pulse: monthly message volume as [label, count] pairs, chronological ──
    month_counts = defaultdict(int)
    for m in messages:
        month_counts[m['timestamp'].strftime('%Y-%m')] += 1
    group_pulse = [
        [datetime.strptime(k, '%Y-%m').strftime('%b %Y'), v]
        for k, v in sorted(month_counts.items())
    ]

    # ── Temporal ──
    rhythm = _conversation_rhythm(messages)
    hour_counts = rhythm.get('hour_counts') or [0] * 24
    peak_hour = max(range(24), key=lambda i: hour_counts[i]) if any(hour_counts) else 0
    peak_hour_label = _hour_label(peak_hour)
    peak_day = rhythm.get('peak_day', 'Unknown')

    # ── Summary figures ──
    span_days = max(rhythm.get('span_days', 0), 1)
    avg_msgs_per_day = round(total / span_days, 1)
    month_counter = Counter(m['timestamp'].strftime('%B %Y') for m in messages)
    most_active_month = month_counter.most_common(1)[0][0] if month_counter else ''

    quietest_name = min(ranked_names, key=lambda p: (counts[p], p)) if ranked_names else None
    quietest_member = (
        {'name': quietest_name, 'count': counts[quietest_name]} if quietest_name else None
    )
    most_active_member = ranked_names[0] if ranked_names else None

    # Per-person media totals (deleted excluded) for the existing "Media Shared" card.
    media_shared = {p: _total_media(media_breakdown_out[p])
                    for p in ranked_names if _total_media(media_breakdown_out[p]) > 0}
    total_media = sum(media_shared.values())

    # Voice-note leader (top audio sender) and per-person deletions.
    top_voice = max(ranked_names, key=lambda p: media_breakdown_out[p]['audio'], default=None)
    voice_note_leader = (
        {'name': top_voice, 'count': media_breakdown_out[top_voice]['audio']}
        if top_voice else {'name': None, 'count': 0}
    )
    deleted_messages = {
        p: media_breakdown_out[p]['deleted']
        for p in ranked_names if media_breakdown_out[p]['deleted'] > 0
    }

    # ── Parity fields (so templates share the 1v1 stat tiles) ──
    # midnight_index is a percentage (0–100) to match the 1v1 metric and the
    # template's `d.midnight_index + '%'` rendering.
    midnight_index = round(
        sum(1 for m in messages if m['timestamp'].hour >= 23 or m['timestamp'].hour < 4)
        / total * 100, 1
    ) if total else 0

    positive_words = {'love', 'nice', 'good', 'great', 'happy', 'amazing', 'awesome', 'bless', 'proud'}
    negative_words = {'hate', 'bad', 'sad', 'angry', 'annoying', 'awful', 'terrible', 'sorry', 'hurt'}

    def _avg_sentiment(msgs):
        pos = neg = 0
        for m in msgs:
            words = set(m['text'].lower().split())
            pos += len(words & positive_words)
            neg += len(words & negative_words)
        return (pos - neg) / (pos + neg + 1)

    mid = total // 2
    sentiment_drift = round(_avg_sentiment(messages[mid:]) - _avg_sentiment(messages[:mid]), 2)

    date_range = {
        'start': messages[0]['timestamp'].strftime('%d %b %Y'),
        'end': messages[-1]['timestamp'].strftime('%d %b %Y'),
        'span_days': span_days,
    }

    # ── Conversation sessions (Phase C1) — across all group messages combined ──
    sessions = compute_sessions(messages)
    sessions_total = len(sessions)
    init_counter = Counter(s['initiator'] for s in sessions)
    end_counter = Counter(s['ender'] for s in sessions)
    top_init = init_counter.most_common(1)[0] if init_counter else (None, 0)
    top_end = end_counter.most_common(1)[0] if end_counter else (None, 0)
    top_session_initiator = {'name': top_init[0], 'count': top_init[1]}
    top_session_ender = {'name': top_end[0], 'count': top_end[1]}

    result = {
        'mode': 'group',
        'participants': ranked_names,
        'participant_count': len(participants),
        'total_messages': total,
        'message_counts': [counts[p] for p in ranked_names],

        # Rankings
        'volume_ranked': volume_ranked,
        'initiation_ranked': initiation_ranked,
        'latency_ranked_minutes': latency_ranked_minutes,
        'activity_shift_ranked': activity_shift_ranked,
        'double_text_ranked': double_text_ranked,
        'emoji_ratio_ranked': emoji_ratio_ranked,
        'textual_dna_ranked': textual_dna_ranked,

        # Group pulse / temporal
        'group_pulse': group_pulse,
        'rhythm': rhythm,
        'peak_day': peak_day,
        'peak_hour': peak_hour,
        'peak_hour_label': peak_hour_label,

        # Summary
        'quietest_member': quietest_member,
        'most_active_member': most_active_member,
        'media_shared': media_shared,
        'avg_msgs_per_day': avg_msgs_per_day,
        'most_active_month': most_active_month,
        'date_range': date_range,

        # Media breakdown (Phase C2)
        'media_breakdown': media_breakdown_out,
        'total_media': total_media,
        'voice_note_leader': voice_note_leader,
        'deleted_messages': deleted_messages,

        # Conversation sessions (Phase C1)
        'sessions_total': sessions_total,
        'top_session_initiator': top_session_initiator,
        'top_session_ender': top_session_ender,

        # Parity
        'midnight_index': midnight_index,
        'sentiment_drift': sentiment_drift,
    }

    # Memorable moments (Phase C3) — condensed for groups.
    result['memorable_moments'] = compute_group_memorable_moments(messages)

    # Call analysis — calls_by_person covers all ranked participants.
    result['call_stats'] = compute_call_stats(call_events or [], ranked_names)

    # Insights last — _group_insights reads back volume_ranked, latency, peak_day, etc.
    result['insights'] = generate_insight(result, 'group')
    return result