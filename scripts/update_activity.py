"""Refresh the profile README activity section.

- Rewrites the <!--ACTIVITY:START--> ... <!--ACTIVITY:END--> block with a table of
  the repos fboucher contributed to in the last 30 days (commits, PRs, issues).
- Writes assets/activity.svg: weekly commits (bars, left axis) and PRs / issues
  (lines, right axis) across all repos for the last 12 weeks.

Run with GH_TOKEN set, or with --demo to render sample data without calling GitHub.
"""
import os, re, sys, json, random, datetime as dt, urllib.request
from collections import defaultdict

USER, TOP, WEEKS, TABLE_DAYS = "fboucher", 5, 12, 30
README, SVG_PATH = "README.md", "assets/activity.svg"

QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      restrictedContributionsCount
      commitContributionsByRepository(maxRepositories:25) {
        repository { nameWithOwner url isPrivate primaryLanguage { name } }
        contributions(first:100) { nodes { occurredAt commitCount } }
      }
      pullRequestContributions(first:100) {
        nodes { occurredAt pullRequest { repository { nameWithOwner url isPrivate primaryLanguage { name } } } }
      }
      issueContributions(first:100) {
        nodes { occurredAt issue { repository { nameWithOwner url isPrivate primaryLanguage { name } } } }
      }
    }
  }
}"""


def fetch(since, now):
    """Return (events, private_count); an event is (yyyy-mm-dd, kind, repo, count)."""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {
            "login": USER, "from": since.isoformat(), "to": now.isoformat()}}).encode(),
        headers={"Authorization": f"bearer {os.environ['GH_TOKEN']}"})
    c = json.load(urllib.request.urlopen(req))["data"]["user"]["contributionsCollection"]
    ev = []
    for r in c["commitContributionsByRepository"]:
        for n in r["contributions"]["nodes"]:
            ev.append((n["occurredAt"][:10], "commits", r["repository"], n["commitCount"]))
    for n in c["pullRequestContributions"]["nodes"]:
        ev.append((n["occurredAt"][:10], "prs", n["pullRequest"]["repository"], 1))
    for n in c["issueContributions"]["nodes"]:
        ev.append((n["occurredAt"][:10], "issues", n["issue"]["repository"], 1))
    return [e for e in ev if not e[2]["isPrivate"]], c["restrictedContributionsCount"]


def demo(since, now):
    """Made-up data so the layout can be previewed without a token."""
    random.seed(7)
    repos = [("FBoucher/2d6-dungeon-app", "C#", 5), ("microsoft/aspire-samples", "C#", 3),
             ("FBoucher/AzUrlShortener", "C#", 2), ("FBoucher/fboucheros.com", "HTML", 2),
             ("cloud5mins/notes", "Markdown", 1)]
    ev, d = [], since.date()
    while d <= now.date():
        for name, lang, w in repos:
            repo = {"nameWithOwner": name, "url": f"https://github.com/{name}",
                    "isPrivate": False, "primaryLanguage": {"name": lang}}
            if random.random() < 0.10 * w:
                ev.append((d.isoformat(), "commits", repo, random.randint(1, 6)))
            if random.random() < 0.025 * w:
                ev.append((d.isoformat(), "prs", repo, 1))
            if random.random() < 0.02 * w:
                ev.append((d.isoformat(), "issues", repo, 1))
        d += dt.timedelta(days=1)
    return ev, 23


# ---------- README table ----------
def table(events, now, private):
    cutoff = (now - dt.timedelta(days=TABLE_DAYS)).date().isoformat()
    per = defaultdict(lambda: {"commits": 0, "prs": 0, "issues": 0})
    meta = {}
    for day, kind, repo, n in events:
        if day >= cutoff:
            per[repo["nameWithOwner"]][kind] += n
            meta[repo["nameWithOwner"]] = repo
    tot = {k: sum(p[k] for p in per.values()) for k in ("commits", "prs", "issues")}
    rows = sorted(per.items(), reverse=True,
                  key=lambda kv: kv[1]["commits"] + 3 * kv[1]["prs"] + 2 * kv[1]["issues"])
    out = [f"_Last {TABLE_DAYS} days: **{tot['commits']}** commits, **{tot['prs']}** PRs, "
           f"**{tot['issues']}** issues (+{private} private contributions)_", "",
           "![Weekly activity: commits, PRs and issues](assets/activity.svg)", "",
           "| Project | Commits | PRs | Issues | Language |", "|---|---:|---:|---:|---|"]
    for name, p in rows[:TOP]:
        r = meta[name]
        lang = (r.get("primaryLanguage") or {}).get("name", "")
        out.append(f"| [{name}]({r['url']}) | {p['commits']} | {p['prs']} | {p['issues']} | {lang} |")
    out.append(f"\n<sub>Updated {now:%Y-%m-%d} by a GitHub Action</sub>")
    return "\n".join(out)


# ---------- SVG chart ----------
def weekly(events, now):
    start = (now - dt.timedelta(weeks=WEEKS - 1)).date()
    start -= dt.timedelta(days=start.weekday())  # align to Monday
    buckets = [{"commits": 0, "prs": 0, "issues": 0} for _ in range(WEEKS)]
    for day, kind, _, n in events:
        i = (dt.date.fromisoformat(day) - start).days // 7
        if 0 <= i < WEEKS:
            buckets[i][kind] += n
    labels = [(start + dt.timedelta(weeks=i)).strftime("%b %d") for i in range(WEEKS)]
    return labels, buckets


def nice_max(v):
    for m in (4, 8, 12, 20, 40, 60, 80, 100, 160, 200, 400, 600, 800, 1000):
        if v <= m:
            return m
    return v


def svg(labels, b):
    W, H = 495, 230
    L, R, T, B = 42, 38, 58, 32
    pw, ph, n = W - L - R, H - T - B, len(b)
    cmax = nice_max(max(x["commits"] for x in b) or 1)
    lmax = nice_max(max(max(x["prs"], x["issues"]) for x in b) or 1)
    slot = pw / n
    bw = slot * 0.55
    xc = lambda i: L + slot * i + slot / 2
    yl = lambda v: T + ph - ph * v / lmax
    font = "'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif"
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t">',
         '<title id="t">Weekly commits, pull requests and issues over the last 12 weeks</title>',
         f"""<style>
  svg{{--bg:#fffefe;--fg:#434d58;--muted:#6e7781;--grid:#e4e2e2;--title:#0a7ea4;--c:#61dafb;--pr:#d63384;--is:#e08a00}}
  @media (prefers-color-scheme:dark){{svg{{--bg:#20232a;--fg:#e6edf3;--muted:#8b949e;--grid:#30363d;--title:#61dafb;--pr:#f07ab8;--is:#f9b233}}}}
  .bg{{fill:var(--bg);stroke:var(--grid)}}
  .t{{font:600 18px {font};fill:var(--title)}}
  .a{{font:400 10px {font};fill:var(--muted)}}
  .lg{{font:400 12px {font};fill:var(--fg)}}
  .g{{stroke:var(--grid);stroke-width:1}}
  .bar{{fill:var(--c);opacity:.9}}
  .pr{{stroke:var(--pr);fill:none;stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}}
  .is{{stroke:var(--is);fill:none;stroke-width:2.5;stroke-dasharray:6 4;stroke-linejoin:round;stroke-linecap:round}}
  .dpr{{fill:var(--pr)}} .dis{{fill:var(--is)}}
</style>""",
         f'<rect class="bg" x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="4.5"/>',
         '<text class="t" x="25" y="34">Weekly activity</text>']
    lx = W - 232
    p += [f'<rect class="bar" x="{lx}" y="23" width="12" height="12" rx="2"/><text class="lg" x="{lx + 17}" y="33">Commits</text>',
          f'<line class="pr" x1="{lx + 84}" y1="29" x2="{lx + 102}" y2="29"/><text class="lg" x="{lx + 107}" y="33">PRs</text>',
          f'<line class="is" x1="{lx + 142}" y1="29" x2="{lx + 160}" y2="29"/><text class="lg" x="{lx + 165}" y="33">Issues</text>']
    for k in range(5):
        y = T + ph * k / 4
        p.append(f'<line class="g" x1="{L}" y1="{y:.1f}" x2="{L + pw}" y2="{y:.1f}"/>')
        p.append(f'<text class="a" x="{L - 6}" y="{y + 3:.1f}" text-anchor="end">{round(cmax * (4 - k) / 4)}</text>')
        p.append(f'<text class="a" x="{L + pw + 6}" y="{y + 3:.1f}">{round(lmax * (4 - k) / 4)}</text>')
    p.append(f'<text class="a" x="8" y="{T - 8}">commits</text>')
    p.append(f'<text class="a" x="{W - 8}" y="{T - 8}" text-anchor="end">PRs / issues</text>')
    for i, x in enumerate(b):
        h = ph * x["commits"] / cmax
        p.append(f'<rect class="bar" x="{xc(i) - bw / 2:.1f}" y="{T + ph - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2">'
                 f'<title>Week of {labels[i]}: {x["commits"]} commits</title></rect>')
        if i % 2 == 1 or i == n - 1:
            p.append(f'<text class="a" x="{xc(i):.1f}" y="{T + ph + 16}" text-anchor="middle">{labels[i]}</text>')
    for kind, cls, dot, word in (("prs", "pr", "dpr", "PRs"), ("issues", "is", "dis", "issues")):
        pts = " ".join(f"{xc(i):.1f},{yl(x[kind]):.1f}" for i, x in enumerate(b))
        p.append(f'<polyline class="{cls}" points="{pts}"/>')
        for i, x in enumerate(b):
            p.append(f'<circle class="{dot}" cx="{xc(i):.1f}" cy="{yl(x[kind]):.1f}" r="3">'
                     f'<title>Week of {labels[i]}: {x[kind]} {word}</title></circle>')
    p.append("</svg>")
    return "\n".join(p)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(weeks=WEEKS + 1)
    events, private = demo(since, now) if "--demo" in sys.argv else fetch(since, now)
    labels, buckets = weekly(events, now)
    os.makedirs(os.path.dirname(SVG_PATH), exist_ok=True)
    with open(SVG_PATH, "w", encoding="utf-8") as f:
        f.write(svg(labels, buckets))
    block = "<!--ACTIVITY:START-->\n" + table(events, now, private) + "\n<!--ACTIVITY:END-->"
    if os.path.exists(README):
        text = open(README, encoding="utf-8").read()
        with open(README, "w", encoding="utf-8") as f:
            f.write(re.sub(r"<!--ACTIVITY:START-->.*?<!--ACTIVITY:END-->", lambda _: block, text, flags=re.S))
    else:
        print(block)


if __name__ == "__main__":
    main()
