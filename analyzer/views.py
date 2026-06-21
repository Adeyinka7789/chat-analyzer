import json
import zipfile
from datetime import datetime
from collections import Counter
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from .parser import (
    parse_whatsapp_file,
    detect_chat_type,
    compute_metrics,
    compute_1to1_metrics,
    compute_group_metrics,
    media_breakdown_from_events,
)

MAX_TXT_BYTES = 10 * 1024 * 1024
MAX_ZIP_BYTES = 150 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024


def extract_chat_text(uploaded_file):
    filename = uploaded_file.name.lower()
    if filename.endswith('.zip'):
        with zipfile.ZipFile(uploaded_file) as zf:
            # WhatsApp bundles exactly one chat .txt (named like "WhatsApp Chat
            # with X.txt" or "_chat.txt"). We read only that file and ignore all
            # media, so the archive's overall (un)compressed size is irrelevant.
            txt_candidates = [
                n for n in zf.namelist()
                if n.lower().endswith('.txt') and not n.startswith('__MACOSX')
            ]
            if not txt_candidates:
                raise ValueError("No chat text file found in archive.")
            chat_file = next(
                (n for n in txt_candidates if n.lower().endswith('_chat.txt')),
                txt_candidates[0],
            )
            # Guard only the text file we actually extract — not the media.
            if zf.getinfo(chat_file).file_size > MAX_UNCOMPRESSED_SIZE:
                raise ValueError("Chat text file too large (uncompressed text exceeds 50 MB).")
            with zf.open(chat_file) as f:
                content = f.read().decode('utf-8', errors='ignore')
            media_file_count = len(zf.namelist()) - len(txt_candidates)
            return content, media_file_count
    else:
        content = uploaded_file.read().decode('utf-8', errors='ignore')
        return content, 0


@ensure_csrf_cookie
def dropzone(request):
    return render(request, 'dropzone.html')


def upload_and_analyze(request):
    if request.method == 'POST' and request.FILES.get('chat_file'):
        uploaded_file = request.FILES['chat_file']
        filename = uploaded_file.name.lower()
        chat_type = request.POST.get('chat_type', '1v1')

        # Reject anything that isn't a WhatsApp export before we touch its bytes.
        if not filename.endswith(('.txt', '.zip')):
            return JsonResponse(
                {'error': 'Invalid file type. Please upload a .txt or .zip file.'},
                status=400,
            )

        if filename.endswith('.zip'):
            if uploaded_file.size > MAX_ZIP_BYTES:
                return JsonResponse(
                    {'error': 'File too large. Maximum compressed size is 150 MB.'},
                    status=413,
                )
        else:
            if uploaded_file.size > MAX_TXT_BYTES:
                return JsonResponse(
                    {'error': 'File too large. Maximum size is 10 MB.'},
                    status=413,
                )

        try:
            content, _zip_media_count = extract_chat_text(uploaded_file)
        except (zipfile.BadZipFile, KeyError):
            return JsonResponse({'error': 'Invalid or corrupt ZIP file.'}, status=400)
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        messages, participants, media_breakdown, media_events, call_events, system_events = parse_whatsapp_file(content)
        if len(messages) < 5:
            return JsonResponse(
                {'error': 'Not enough messages to analyze (need at least 5).'},
                status=400,
            )

        # Auto-detect from the file itself; the user's toggle is only a hint and is
        # intentionally ignored for the actual analysis path.
        detected_type = detect_chat_type(messages, system_events)

        metrics = compute_metrics(messages, participants, detected_type, media_breakdown, call_events)
        if metrics is None:
            return JsonResponse(
                {'error': 'Could not identify at least two participants.'},
                status=400,
            )

        # If detection overrode the user's selection, surface it (don't switch
        # silently). These keys ride along in the metrics dict so the dashboard —
        # which renders from the session, not this response — can show a notice.
        if detected_type != chat_type:
            detected_label = 'group' if detected_type == 'group' else '1-on-1'
            metrics['type_mismatch'] = True
            metrics['detected'] = detected_type
            metrics['selected'] = chat_type
            metrics['message'] = (
                "We detected this is a {0} chat and analyzed it as one. "
                "{1} analysis is now showing."
            ).format(detected_label, detected_label.capitalize())

        # Privacy posture: the parsed messages (sender + timestamp + text) are kept
        # ONLY in the in-memory session (locmem cache, never written to disk) so the
        # /filter/ endpoint can recompute metrics for a date range without re-uploading.
        # The session — and therefore this data — expires after SESSION_COOKIE_AGE
        # (1 hour). This is what the footer claim reflects.
        request.session['analysis'] = metrics
        request.session['chat_type'] = detected_type
        request.session['parsed_messages'] = [
            {
                'sender': m['sender'],
                'timestamp': m['timestamp'].isoformat(),
                'text': m['text'],
            }
            for m in messages
        ]
        # Media events are metadata only (sender, timestamp, type — no text), so the
        # /filter/ endpoint can recompute the media breakdown for a date range.
        request.session['media_events'] = [
            {
                'sender': ev['sender'],
                'timestamp': ev['timestamp'].isoformat(),
                'type': ev['type'],
            }
            for ev in media_events
        ]
        # Call events are metadata only (caller, timestamp, type, outcome,
        # duration — no text); timestamps are already ISO strings from the parser.
        request.session['call_events'] = call_events
        return JsonResponse(metrics)

    return JsonResponse({'error': 'No file uploaded'}, status=400)


@ensure_csrf_cookie
def dashboard(request):
    analysis = request.session.get('analysis')
    if not analysis:
        return render(request, 'dropzone.html', {'error': 'No analysis found. Please upload a file first.'})
    
    # Ensure all new fields exist (for backwards compatibility)
    if 'word_battle' not in analysis:
        # Add defaults for old data
        analysis['word_battle'] = {'avg_words': [0, 0], 'longest_message': [0, 0], 'unique_words': [0, 0]}
        analysis['word_histogram'] = [[0,0,0,0,0], [0,0,0,0,0]]
        analysis['question_ratio'] = [0, 0]
        analysis['abbrev_density'] = [0, 0]
        analysis['sentiment_volatility'] = 0
        analysis['positivity_ratio'] = 0
        analysis['sentiment_over_time'] = []
        analysis['burstiness_score'] = 0
        analysis['predictability_score'] = 0
        analysis['best_time_to_message'] = ["N/A", "N/A"]
        analysis['turn_equality'] = 50
        analysis['peak_hour_text'] = "N/A"
        analysis['best_day'] = "N/A"

    # health_score is a structured dict ({overall, engagement, balance, sentiment,
    # consistency}). Old cached sessions stored it as a bare int — normalise so the
    # dashboard can always read health_score.overall / .engagement / etc.
    hs = analysis.get('health_score')
    if not isinstance(hs, dict):
        analysis['health_score'] = {
            'overall': hs if isinstance(hs, int) else 50,
            'engagement': 50, 'balance': 50, 'sentiment': 50, 'consistency': 50,
        }

    mode = analysis.get('mode', '1v1')
    template = 'dashboard_group.html' if mode == 'group' else 'dashboard.html'
    return render(request, template, {'data': json.dumps(analysis)})


def analytics(request):
    analysis = request.session.get('analysis')
    if not analysis:
        return render(request, 'dropzone.html', {'error': 'No analysis found. Please upload a file first.'})
    return render(request, 'analytics.html', {'data': json.dumps(analysis)})


def processing(request):
    return render(request, 'processing.html')


def filter_analysis(request):
    """Recompute metrics for a date range from the in-memory parsed messages.

    Accepts a POST with {'date_from': 'YYYY-MM-DD', 'date_to': 'YYYY-MM-DD'} and
    returns the same metrics shape as the upload endpoint, computed over only the
    messages whose date falls within the (inclusive) range. No file is re-read and
    nothing is written to disk — the parsed messages live in the session cache.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)

    analysis = request.session.get('analysis')
    parsed = request.session.get('parsed_messages')
    if not analysis or parsed is None:
        return JsonResponse(
            {'error': 'Your session has expired. Please upload your chat again.'},
            status=400,
        )

    # Body may be JSON (fetch) or form-encoded.
    try:
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = request.POST
    date_from = payload.get('date_from')
    date_to = payload.get('date_to')
    if not date_from or not date_to:
        return JsonResponse({'error': 'date_from and date_to are required.'}, status=400)

    try:
        d_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        d_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD.'}, status=400)
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    # Rebuild message dicts (datetime restored) for those inside the range.
    messages = []
    for m in parsed:
        ts = datetime.fromisoformat(m['timestamp'])
        if d_from <= ts.date() <= d_to:
            messages.append({'timestamp': ts, 'sender': m['sender'], 'text': m['text']})

    if not messages:
        return JsonResponse({'error': 'No messages in the selected date range.'}, status=400)

    # Media breakdown for the range: filter the stored media events by date, then
    # aggregate them back into the {sender: {type: count}} shape compute_* expects.
    media_in_range = [
        ev for ev in (request.session.get('media_events') or [])
        if d_from <= datetime.fromisoformat(ev['timestamp']).date() <= d_to
    ]
    media_breakdown = media_breakdown_from_events(media_in_range)

    # Call events for the range — same date-filter pattern as media events.
    call_in_range = [
        ev for ev in (request.session.get('call_events') or [])
        if d_from <= datetime.fromisoformat(ev['timestamp']).date() <= d_to
    ]

    # Preserve the original participant order (A/B for 1v1, ranked for group) so
    # the dashboard's per-person assignments stay stable across filters.
    participants = analysis.get('participants') or []

    if analysis.get('mode') == 'group':
        filtered = compute_group_metrics(messages, participants, media_breakdown, call_in_range)
    else:
        filtered = compute_1to1_metrics(messages, participants, media_breakdown, call_in_range)

    return JsonResponse(filtered)


def how_to_export(request):
    return render(request, 'how_to_export.html')


# ─────────────────────────────────────────────────────────────
# SHAREABLE SUMMARY CARD (Phase D2)
# ─────────────────────────────────────────────────────────────

def _combined_top_emoji(*emoji_lists):
    """Merge several [[emoji, count], …] lists into a single most-used emoji."""
    counter = Counter()
    for lst in emoji_lists:
        for pair in (lst or []):
            counter[pair[0]] += pair[1]
    return counter.most_common(1)[0][0] if counter else '—'


def _card_context_1v1(a):
    pc = a.get('participants') or ['?', '?']
    counts = a.get('message_counts') or [0, 0]
    total = a.get('total_messages') or 0
    mm = a.get('memorable_moments') or {}

    share = [
        round(counts[0] / total * 100) if total else 0,
        round(counts[1] / total * 100) if total else 0,
    ]
    leader_idx = 0 if counts[0] >= counts[1] else 1

    # Highlight: prefer biggest day, else first-message date.
    biggest = mm.get('biggest_day')
    first = mm.get('first_message')
    if biggest:
        highlight = f"🔥 {biggest['date_label']} — {biggest['msg_count']:,} messages"
    elif first:
        highlight = f"🗓 First message on {first['date_label']}"
    else:
        highlight = None

    # Response speed: latency_minutes[i] maps to participants[i] (same convention
    # as the dashboard's Response Velocity card). Faster = smaller value.
    lm = a.get('latency_minutes') or [None, None]
    valid = [(pc[i], lm[i]) for i in range(2) if lm[i] is not None]
    if valid:
        faster_name, faster_min = min(valid, key=lambda x: x[1])
        speed_text = f"{faster_name} replies faster — avg {faster_min:g} min"
    else:
        speed_text = None

    return {
        'name_a': pc[0],
        'name_b': pc[1],
        'total_messages': f"{total:,}",
        'span_days': (a.get('rhythm') or {}).get('span_days', 0),
        'most_active_month': a.get('most_active_month') or '—',
        'top_emoji': _combined_top_emoji(a.get('top_emojis_A'), a.get('top_emojis_B')),
        'count_a': f"{counts[0]:,}",
        'count_b': f"{counts[1]:,}",
        'share_a': share[0],
        'share_b': share[1],
        'leader_a': leader_idx == 0,
        'leader_b': leader_idx == 1,
        'highlight': highlight,
        'speed_text': speed_text,
    }


def _card_context_group(a):
    pc = a.get('participants') or ['?']
    total = a.get('total_messages') or 0
    mm = a.get('memorable_moments') or {}

    others = max(len(pc) - 1, 0)
    group_name = f"{pc[0]} & {others} other{'' if others == 1 else 's'}"

    # No group-wide emoji frequency exists; use the most common member-favorite.
    err = a.get('emoji_ratio_ranked') or []
    fav = Counter(e['top_emoji'] for e in err if e.get('top_emoji'))
    top_emoji = fav.most_common(1)[0][0] if fav else '—'

    biggest = mm.get('biggest_day')
    if biggest:
        highlight = f"🔥 {biggest['date_label']} — {biggest['msg_count']:,} messages"
    else:
        highlight = None

    podium = [
        {'name': m['name'], 'count': f"{m['count']:,}", 'pct': m.get('pct', 0)}
        for m in (a.get('volume_ranked') or [])[:3]
    ]

    return {
        'group_name': group_name,
        'total_messages': f"{total:,}",
        'participant_count': a.get('participant_count') or len(pc),
        'most_active_month': a.get('most_active_month') or '—',
        'top_emoji': top_emoji,
        'podium': podium,
        'highlight': highlight,
        'peak_day': a.get('peak_day') or '—',
        'peak_hour_label': a.get('peak_hour_label') or '—',
    }


def share_card(request):
    """Read-only standalone summary card rendered from the session analysis."""
    analysis = request.session.get('analysis')
    if not analysis:
        return redirect('dropzone')

    if analysis.get('mode') == 'group':
        return render(request, 'card_group.html', _card_context_group(analysis))
    return render(request, 'card_1v1.html', _card_context_1v1(analysis))
