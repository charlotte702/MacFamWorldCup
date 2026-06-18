#!/usr/bin/env python3
"""
World Cup 2026 Sweepstakes — auto-updater
Fetches latest results from football-data.org and patches index.html FALLBACK block.
Run by GitHub Actions on a schedule; commits the diff so Netlify redeploys automatically.
"""

import os, re, json, datetime, urllib.request, urllib.error

API_KEY  = os.environ["FD_API_KEY"]
API_BASE = "https://api.football-data.org/v4"
COMP_CODES = ["WC", "2000"]

# ── People & teams ─────────────────────────────────────────────────────────
PEOPLE = {
    "Jace":     ["Haiti","Iraq","Austria","Senegal","Argentina"],
    "Nikolai":  ["Bosnia and Herzegovina","Czech Republic","Norway","Uruguay","France"],
    "Brodie":   ["Jordan","Scotland","Turkey","Iran","Belgium"],
    "Jenson":   ["Ghana","Paraguay","Panama","South Korea","Morocco"],
    "Stuart M": ["Curacao","Qatar","Ivory Coast","Switzerland","Portugal"],
    "Charlotte":["New Zealand","South Africa","Ecuador","Mexico","England"],
    "Stuart P": ["DR Congo","Algeria","Colombia","Spain"],
    "Fran":     ["Tunisia","Canada","Croatia","Netherlands"],
    "Elaine":   ["Saudi Arabia","Uzbekistan","Egypt","United States","Brazil"],
    "David":    ["Cape Verde","Sweden","Australia","Japan","Germany"],
}

# Broad alias map — API name (lowercase stripped) → sweepstake name
ALIASES = {
    "korea republic":                   "South Korea",
    "republic of korea":                "South Korea",
    "cote d'ivoire":                    "Ivory Coast",
    "côte d'ivoire":                    "Ivory Coast",
    "ivory coast":                      "Ivory Coast",
    "usa":                              "United States",
    "united states":                    "United States",
    "ir iran":                          "Iran",
    "iran":                             "Iran",
    "cabo verde":                       "Cape Verde",
    "cape verde":                       "Cape Verde",
    "cape verde islands":               "Cape Verde",
    "dr congo":                         "DR Congo",
    "congo dr":                         "DR Congo",
    "democratic republic of congo":     "DR Congo",
    "congo, democratic republic of the":"DR Congo",
    "bosnia-herzegovina":               "Bosnia and Herzegovina",
    "bosnia and herzegovina":           "Bosnia and Herzegovina",
    "czech republic":                   "Czech Republic",
    "czechia":                          "Czech Republic",
    "curacao":                          "Curacao",
    "curaçao":                          "Curacao",
    "new zealand":                      "New Zealand",
    "saudi arabia":                     "Saudi Arabia",
    "south africa":                     "South Africa",
    "south korea":                      "South Korea",
}

# All sweepstake team names (lowercased) for reverse lookup
SWEEPSTAKE_TEAMS = {}
for person, teams in PEOPLE.items():
    for t in teams:
        SWEEPSTAKE_TEAMS[t.lower()] = t

def normalise(name):
    """Convert any API team name to the sweepstake team name."""
    if not name:
        return name
    low = name.lower().strip()
    # Check aliases first
    if low in ALIASES:
        return ALIASES[low]
    # Check if it already matches a sweepstake team directly
    if low in SWEEPSTAKE_TEAMS:
        return SWEEPSTAKE_TEAMS[low]
    # Return original if no match
    return name

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
                print(f"Got {len(matches)} matches from code {code}")
                return matches
        except Exception as e:
            print(f"Code {code} failed: {e}")
    raise RuntimeError("No match data from any competition code")

def load_scorers():
    for code in COMP_CODES:
        try:
            data = api_fetch(f"/competitions/{code}/scorers?limit=20")
            scorers = data.get("scorers", [])
            if scorers:
                print(f"Got {len(scorers)} scorers from code {code}")
                return scorers
        except Exception as e:
            print(f"Scorers code {code} failed: {e}")
    return []

def fmt_date(utc):
    try:
        dt = datetime.datetime.fromisoformat(utc.replace("Z", "+00:00"))
        return dt.strftime("%d %b").lstrip("0")
    except Exception:
        return ""

def build_scores(matches, scorers):
    team_pts    = {}
    team_notes  = {}
    team_played = set()

    finished = [m for m in matches if m.get("status") == "FINISHED"]
    print(f"Finished matches: {len(finished)}")

    for m in finished:
        ft = m.get("score", {}).get("fullTime", {})
        h_goals = ft.get("home")
        a_goals = ft.get("away")
        if h_goals is None or a_goals is None:
            continue

        h_raw = m.get("homeTeam", {}).get("name", "")
        a_raw = m.get("awayTeam", {}).get("name", "")
        hn = normalise(h_raw)
        an = normalise(a_raw)
        date = fmt_date(m.get("utcDate", ""))

        # Debug: print all teams to help spot name issues
        print(f"  {h_raw!r} -> {hn!r}  vs  {a_raw!r} -> {an!r}  ({h_goals}-{a_goals})")

        if h_goals > a_goals:
            h_pts, a_pts = 3, 0
            note_h = f"{h_goals}-{a_goals} vs {an} ({date})"
            note_a = f"0-{h_goals}-{a_goals} to {hn} ({date})"
        elif a_goals > h_goals:
            h_pts, a_pts = 0, 3
            note_h = f"0-{h_goals}-{a_goals} to {an} ({date})"
            note_a = f"{a_goals}-{h_goals} vs {hn} ({date})"
        else:
            h_pts = a_pts = 1
            note_h = f"{h_goals}-{a_goals} draw vs {an} ({date})"
            note_a = f"{a_goals}-{h_goals} draw vs {hn} ({date})"

        team_pts[hn]  = team_pts.get(hn, 0) + h_pts
        team_pts[an]  = team_pts.get(an, 0) + a_pts
        team_played.add(hn)
        team_played.add(an)
        team_notes[hn] = note_h
        team_notes[an] = note_a

    # Ensure all sweepstake teams appear (0 if not yet played)
    for teams in PEOPLE.values():
        for t in teams:
            if t not in team_pts:
                team_pts[t] = 0

    print(f"\nTeam points summary:")
    for k, v in sorted(team_pts.items()):
        played = "played" if k in team_played else "not yet played"
        print(f"  {k}: {v}pts ({played})")

    # Scorers
    scorer_list = []
    for s in scorers[:10]:
        player = s.get("player", {}).get("name", "Unknown")
        team   = normalise(s.get("team", {}).get("name", ""))
        goals  = s.get("goals") or s.get("numberOfGoals") or 0
        scorer_list.append({"player": player, "team": team, "goals": goals})

    return team_pts, team_notes, list(team_played), scorer_list

def extract_existing_drama(html_path):
    """Pull the existing drama array out of index.html so we preserve it."""
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"drama:\s*\[(.*?)\]", content, re.DOTALL)
        if m:
            return m.group(0)  # keep the whole "drama: [...]" string
    except Exception as e:
        print(f"Could not extract drama: {e}")
    return None

def build_new_drama_items(matches, scorers):
    """Generate drama items for notable NEW events (hat-tricks, 5+ margins)."""
    items = []
    # Hat-tricks
    for s in scorers[:20]:
        if (s.get("goals") or 0) >= 3:
            player = s.get("player", {}).get("name", "Unknown")
            team   = normalise(s.get("team", {}).get("name", ""))
            owner  = next((p for p, ts in PEOPLE.items() if team in ts), "")
            label  = f"{owner}'s {team}" if owner else team
            items.append({"type": "big", "text": f"HAT-TRICK! {player} ({label}) - {s['goals']} goals!"})
    # Big wins 5+ margin
    for m in matches:
        if m.get("status") != "FINISHED":
            continue
        ft = m.get("score", {}).get("fullTime", {})
        h, a = ft.get("home"), ft.get("away")
        if h is None or a is None or abs(h-a) < 5:
            continue
        hn = normalise(m.get("homeTeam", {}).get("name", ""))
        an = normalise(m.get("awayTeam", {}).get("name", ""))
        date = fmt_date(m.get("utcDate", ""))
        win, lose = (hn, an) if h > a else (an, hn)
        ws, ls = (h, a) if h > a else (a, h)
        wown = next((p for p, ts in PEOPLE.items() if win in ts), "")
        lown = next((p for p, ts in PEOPLE.items() if lose in ts), "")
        wlabel = f"{wown}'s {win}" if wown else win
        llabel = f"{lown}'s {lose}" if lown else lose
        items.append({"type": "big", "text": f"{wlabel} {ws}-{ls} {llabel} ({date}) - what a hiding!"})
    return items

def render_drama_js(items):
    lines = []
    for d in items:
        te = d["text"].replace("'", "\\'")
        lines.append(f"    {{ type:'{d['type']}', text:'{te}' }}")
    return "  drama: [\n" + ",\n".join(lines) + "\n  ]"

def render_fallback_block(team_pts, team_notes, team_played, scorers, drama_js, last_updated):
    def esc(s): return str(s).replace("\\", "\\\\").replace("'", "\\'")

    pts_lines = [f"    '{esc(k)}': {v}" for k, v in team_pts.items()]
    pts_js = "  teamPts: {\n" + ",\n".join(pts_lines) + "\n  }"

    note_lines = [f"    '{esc(k)}': '{esc(v)}'" for k, v in team_notes.items()]
    notes_js = "  teamNotes: {\n" + ",\n".join(note_lines) + "\n  }"

    played_items = ", ".join(f"'{esc(t)}'" for t in sorted(team_played))
    played_js = f"  teamPlayed: new Set([{played_items}])"

    scorer_lines = [
        f"    {{ player:{{name:'{esc(s['player'])}'}}, team:{{name:'{esc(s['team'])}'}}, goals:{s['goals']} }}"
        for s in scorers
    ]
    scorers_js = "  scorers: [\n" + ",\n".join(scorer_lines) + "\n  ]"

    lu_js = f"  lastUpdated: '{esc(last_updated)}'"

    return (
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

def patch_html(html_path, new_block):
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r"// ═+\n// HARDCODED FALLBACK.*?// ═+\nconst FALLBACK = \{.*?\};"
    new_content, n = re.subn(pattern, new_block, content, flags=re.DOTALL)
    if n == 0:
        raise RuntimeError("Could not find FALLBACK block to replace")
    print(f"Patched FALLBACK block ({n} replacement)")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(new_content)

def main():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")

    print("Fetching matches...")
    matches = load_matches()
    print("Fetching scorers...")
    scorers = load_scorers()

    print("\nBuilding scores...")
    team_pts, team_notes, team_played, scorer_list = build_scores(matches, scorers)

    # Preserve existing drama + add any new notable items
    existing_drama_str = extract_existing_drama(html_path)
    new_items = build_new_drama_items(matches, scorers)

    if existing_drama_str and new_items:
        # Inject new items at the top of existing drama array
        new_lines = render_drama_js(new_items)
        # Replace closing ] with new items + original content
        drama_js = existing_drama_str  # keep as-is for now
    elif existing_drama_str:
        drama_js = existing_drama_str
    else:
        drama_js = render_drama_js(new_items)

    today = datetime.datetime.utcnow().strftime("%d %B %Y").lstrip("0")
    last_updated = f"{today} — auto-updated by GitHub Actions"

    block = render_fallback_block(team_pts, team_notes, team_played, scorer_list, drama_js, last_updated)

    print("\nPatching index.html...")
    patch_html(html_path, block)
    print(f"Done — {last_updated}")

if __name__ == "__main__":
    main()
