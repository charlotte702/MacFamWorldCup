#!/usr/bin/env python3
"""
World Cup 2026 Sweepstakes — auto-updater
Fetches latest results from football-data.org and patches index.html FALLBACK block.
Run by GitHub Actions on a schedule; commits the diff so Netlify redeploys automatically.
"""

import os, re, json, datetime, urllib.request, urllib.error

API_KEY  = os.environ["FD_API_KEY"]   # set as GitHub Actions secret
API_BASE = "https://api.football-data.org/v4"
COMP_CODES = ["WC", "2000"]

# ── People & teams (must mirror index.html PEOPLE object) ──────────────────
PEOPLE = {
    "Jace":     ["Haiti","Iraq","Austria","Senegal","Argentina"],
    "Nikolai":  ["Bosnia and Herzegovina","Czech Republic","Norway","Uruguay","France"],
    "Brodie":   ["Jordan","Scotland","Turkey","Iran","Belgium"],
    "Jenson":   ["Ghana","Paraguay","Panama","South Korea","Morocco"],
    "Stuart M": ["Curaçao","Qatar","Côte d'Ivoire","Switzerland","Portugal"],
    "Charlotte":["New Zealand","South Africa","Ecuador","Mexico","England"],
    "Stuart P": ["DR Congo","Algeria","Colombia","Spain"],
    "Fran":     ["Tunisia","Canada","Croatia","Netherlands"],
    "Elaine":   ["Saudi Arabia","Uzbekistan","Egypt","United States","Brazil"],
    "David":    ["Cape Verde","Sweden","Australia","Japan","Germany"],
}

ALIASES = {
    # API name → sweepstake name
    "Korea Republic":       "South Korea",
    "Côte d'Ivoire":        "Ivory Coast",
    "Cote d'Ivoire":        "Ivory Coast",
    "USA":                  "United States",
    "IR Iran":              "Iran",
    "Bosnia and Herzegovina":"Bosnia and Herzegovina",
}

def normalise(name):
    return ALIASES.get(name, name)

def api_fetch(path):
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={"X-Auth-Token": API_KEY})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def load_matches():
    for code in COMP_CODES:
        try:
            data = api_fetch(f"/competitions/{code}/matches")
            matches = data.get("matches", [])
            if matches:
                print(f"✅ Got {len(matches)} matches from code {code}")
                return matches
        except Exception as e:
            print(f"⚠️  Code {code} failed: {e}")
    raise RuntimeError("No match data from any competition code")

def load_scorers():
    for code in COMP_CODES:
        try:
            data = api_fetch(f"/competitions/{code}/scorers?limit=20")
            scorers = data.get("scorers", [])
            if scorers:
                print(f"✅ Got {len(scorers)} scorers from code {code}")
                return scorers
        except Exception as e:
            print(f"⚠️  Scorers code {code} failed: {e}")
    return []

def build_fallback(matches, scorers):
    team_pts   = {}   # normalised name → pts
    team_notes = {}
    team_played = set()

    for m in matches:
        if m.get("status") != "FINISHED":
            continue
        ft = m.get("score", {}).get("fullTime", {})
        h_goals = ft.get("home")
        a_goals = ft.get("away")
        if h_goals is None or a_goals is None:
            continue

        h_raw = m.get("homeTeam", {}).get("name", "")
        a_raw = m.get("awayTeam", {}).get("name", "")
        hn = normalise(h_raw)
        an = normalise(a_raw)

        date_str = ""
        utc = m.get("utcDate", "")
        if utc:
            try:
                dt = datetime.datetime.fromisoformat(utc.replace("Z", "+00:00"))
                date_str = dt.strftime("%-d %b")
            except Exception:
                pass

        if h_goals > a_goals:
            h_pts, a_pts = 3, 0
            note_h = f"{h_goals}-{a_goals} vs {an} ({date_str})"
            note_a = f"0-{h_goals}-{a_goals} to {hn} ({date_str})"
        elif a_goals > h_goals:
            h_pts, a_pts = 0, 3
            note_h = f"0-{h_goals}-{a_goals} to {an} ({date_str})"
            note_a = f"{a_goals}-{h_goals} vs {hn} ({date_str})"
        else:
            h_pts = a_pts = 1
            note_h = f"{h_goals}-{a_goals} draw vs {an} ({date_str})"
            note_a = f"{a_goals}-{h_goals} draw vs {hn} ({date_str})"

        team_pts[hn]  = team_pts.get(hn, 0)  + h_pts
        team_pts[an]  = team_pts.get(an, 0)  + a_pts
        team_played.add(hn)
        team_played.add(an)

        # Keep most recent note per team
        team_notes[hn] = note_h
        team_notes[an] = note_a

    # Make sure all sweepstake teams appear (0 pts if not yet played)
    all_teams = [t for teams in PEOPLE.values() for t in teams]
    for t in all_teams:
        n = normalise(t)
        if n not in team_pts:
            team_pts[n] = 0

    # Scorers → simple list
    scorer_list = []
    for s in scorers[:10]:
        player = s.get("player", {}).get("name", "Unknown")
        team   = normalise(s.get("team", {}).get("name", ""))
        goals  = s.get("goals", 0) or s.get("numberOfGoals", 0)
        scorer_list.append({"player": player, "team": team, "goals": goals})

    # Drama — auto-generate top items
    drama = []
    # Hat-tricks from scorers
    for s in scorer_list:
        if s["goals"] >= 3:
            # Find who owns this team
            owner = next((p for p, ts in PEOPLE.items() for t in ts if normalise(t) == s["team"]), "")
            label = f"{owner}'s {s['team']}" if owner else s["team"]
            drama.append({
                "type": "big",
                "text": f"🎩 HAT-TRICK! {s['player']} ({label}) — {s['goals']} goals!"
            })

    # Big wins (5+ goal margin)
    for m in matches:
        if m.get("status") != "FINISHED":
            continue
        ft = m.get("score", {}).get("fullTime", {})
        h, a = ft.get("home"), ft.get("away")
        if h is None or a is None:
            continue
        diff = abs(h - a)
        hn = normalise(m.get("homeTeam", {}).get("name", ""))
        an = normalise(m.get("awayTeam", {}).get("name", ""))
        utc = m.get("utcDate", "")
        date_str = ""
        if utc:
            try:
                dt = datetime.datetime.fromisoformat(utc.replace("Z", "+00:00"))
                date_str = dt.strftime("%-d %b")
            except Exception:
                pass
        win, lose = (hn, an) if h > a else (an, hn)
        ws, ls = (h, a) if h > a else (a, h)
        wown = next((p for p, ts in PEOPLE.items() if any(normalise(t) == win for t in ts)), "")
        lown = next((p for p, ts in PEOPLE.items() if any(normalise(t) == lose for t in ts)), "")
        wlabel = f"{wown}'s {win}" if wown else win
        llabel = f"{lown}'s {lose}" if lown else lose
        if diff >= 5:
            drama.append({
                "type": "big",
                "text": f"💥 {wlabel} {ws}-{ls} {llabel} ({date_str}) — what a hiding!"
            })

    drama = drama[:8]  # cap at 8 items

    # Build JS-ready lastUpdated string
    today = datetime.datetime.utcnow().strftime("%-d %B %Y")
    last_updated = f"{today} — auto-updated by GitHub Actions"

    return team_pts, team_notes, list(team_played), scorer_list, drama, last_updated

def render_js_object(d, indent=4):
    """Render a Python dict as a JS object literal."""
    pad = " " * indent
    lines = []
    for k, v in d.items():
        k_esc = k.replace("'", "\\'")
        if isinstance(v, int):
            lines.append(f"{pad}'{k_esc}':{v}")
        else:
            v_esc = str(v).replace("'", "\\'")
            lines.append(f"{pad}'{k_esc}':'{v_esc}'")
    return "{\n" + ",\n".join(lines) + "\n  }"

def render_fallback_block(team_pts, team_notes, team_played, scorers, drama, last_updated):
    # teamPts
    pts_lines = []
    for k, v in team_pts.items():
        pts_lines.append(f"    '{k.replace(chr(39), chr(92)+chr(39))}': {v}")
    pts_js = "  teamPts: {\n" + ",\n".join(pts_lines) + "\n  }"

    # teamNotes
    note_lines = []
    for k, v in team_notes.items():
        ke = k.replace("'", "\\'")
        ve = v.replace("'", "\\'")
        note_lines.append(f"    '{ke}': '{ve}'")
    notes_js = "  teamNotes: {\n" + ",\n".join(note_lines) + "\n  }"

    # teamPlayed
    played_items = ", ".join(f"'{t.replace(chr(39), chr(92)+chr(39))}'" for t in sorted(team_played))
    played_js = f"  teamPlayed: new Set([{played_items}])"

    # scorers
    scorer_lines = []
    for s in scorers:
        pn = s['player'].replace("'", "\\'")
        tn = s['team'].replace("'", "\\'")
        scorer_lines.append(f"    {{ player:{{name:'{pn}'}}, team:{{name:'{tn}'}}, goals:{s['goals']} }}")
    scorers_js = "  scorers: [\n" + ",\n".join(scorer_lines) + "\n  ]"

    # lastUpdated
    lu_esc = last_updated.replace("'", "\\'")
    lu_js = f"  lastUpdated: '{lu_esc}'"

    # drama
    drama_lines = []
    for d in drama:
        te = d['text'].replace("'", "\\'").replace("\\\\", "\\")
        drama_lines.append(f"    {{ type:'{d['type']}', text:'{te}' }}")
    drama_js = "  drama: [\n" + ",\n".join(drama_lines) + "\n  ]"

    block = (
        "// ════════════════════════════════════════════\n"
        "// HARDCODED FALLBACK — auto-updated by GitHub Actions\n"
        "// Used when API is unavailable / not yet covering WC2026\n"
        "// ════════════════════════════════════════════\n"
        "const FALLBACK = {\n"
        f"  // pts = cumulative sweepstake points (3=90min win, 1=draw, 0=loss)\n"
        f"{pts_js},\n"
        f"{notes_js},\n"
        f"{played_js},\n"
        f"{scorers_js},\n"
        f"{lu_js},\n"
        f"{drama_js},\n"
        "};"
    )
    return block

def patch_html(html_path, new_fallback_block):
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = (
        r"// ═+\n"
        r"// HARDCODED FALLBACK.*?\n"
        r"(?:// .*?\n)*"
        r"// ═+\n"
        r"const FALLBACK = \{.*?\};"
    )
    new_content, n = re.subn(pattern, new_fallback_block, content, flags=re.DOTALL)
    if n == 0:
        raise RuntimeError("Could not find FALLBACK block in index.html — pattern didn't match")
    print(f"✅ Patched FALLBACK block ({n} replacement(s))")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(new_content)

def main():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    print("🔄 Fetching match data…")
    matches = load_matches()
    print("🔄 Fetching scorer data…")
    scorers = load_scorers()
    print("🔄 Building fallback…")
    team_pts, team_notes, team_played, scorer_list, drama, last_updated = build_fallback(matches, scorers)
    block = render_fallback_block(team_pts, team_notes, team_played, scorer_list, drama, last_updated)
    print("🔄 Patching index.html…")
    patch_html(html_path, block)
    print(f"✅ Done — {last_updated}")

if __name__ == "__main__":
    main()
