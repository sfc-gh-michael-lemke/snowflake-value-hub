#!/usr/bin/env python3
"""
update-catalog.py — Rebuild catalog-data.js from all repos that have value-realization.html.

Usage:
    python3 update-catalog.py [--push] [--org ORG] [--token TOKEN]

Options:
    --push          Commit and push updated catalog-data.js to gh-pages (default: dry run)
    --org           GitHub org/user (default: sfc-gh-michael-lemke)
    --token         GitHub personal access token (or set GITHUB_TOKEN env var)
                    Required only if you hit rate limits (60 req/hr unauthenticated)

How it works:
    1. Lists all public repos for the org via GitHub API
    2. For each repo: tries to fetch value-realization.html from main/master
    3. Parses the HTML to extract all catalog fields
    4. Writes catalog-data.js alongside this script
    5. Optionally commits + pushes to gh-pages
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser


# ── Config ────────────────────────────────────────────────────────────────────

ORG = "sfc-gh-michael-lemke"
SLIDE_FILE = "value-realization.html"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog-data.js")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def http_get(url, headers=None):
    """Fetch URL, return (status_code, text). Never raises."""
    req = urllib.request.Request(url, headers=headers or {})
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("User-Agent", "update-catalog/1.0")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def api_get(path):
    """Call GitHub API, return parsed JSON or None."""
    status, body = http_get(f"https://api.github.com{path}",
                            headers={"Accept": "application/vnd.github.v3+json"})
    if status == 200:
        try:
            return json.loads(body)
        except Exception:
            return None
    return None


# ── List repos ────────────────────────────────────────────────────────────────

def list_repos(org):
    """Return list of repo names. Fetches all repos (public+private if token present)."""
    repos = []
    page = 1
    # Use /user/repos when authenticated (returns private repos too)
    # Use /users/{org}/repos when unauthenticated (public only)
    if GITHUB_TOKEN:
        path_tmpl = "/user/repos?affiliation=owner&per_page=100&page={page}"
    else:
        path_tmpl = f"/users/{org}/repos?type=public&per_page=100&page={{page}}"
    while True:
        data = api_get(path_tmpl.format(page=page))
        if not data:
            break
        repos.extend(r["name"] for r in data)
        if len(data) < 100:
            break
        page += 1
    return repos


# ── Fetch slide HTML ──────────────────────────────────────────────────────────

def fetch_slide(org, repo):
    """Return (html_text, branch, raw_url) or (None, None, None)."""
    for branch in ("main", "master"):
        raw_url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{SLIDE_FILE}"
        status, body = http_get(raw_url)
        if status == 200 and body.strip():
            return body, branch, raw_url
    return None, None, None


# ── HTML parser ───────────────────────────────────────────────────────────────

class SlideParser(HTMLParser):
    """
    Extracts catalog fields from a value-realization.html slide.

    Target elements (in document order):
        .badge          → persona (first occurrence only)
        .hero-title     → project_name (text before <span>), tagline (inside <span>)
        .hero-tagline   → summary
        .panel-heading  → challenge_heading (1st), capability_heading (2nd), outcome_heading (3rd)
        .bullet-list li → bullets (each li text)
        .chip           → chips
        .outcome-text strong → outcomes (bold label per outcome)
        .step-text      → next_steps
    """

    def __init__(self):
        super().__init__()
        self._stack = []          # current open element classes
        self._capture = None      # which field we're capturing text into
        self._in_span = False     # inside hero-title span (= tagline)
        self._hero_title_buf = "" # raw text of hero-title before span
        self._panel_heading_count = 0

        # Output fields
        self.persona = ""
        self.project_name = ""
        self.tagline = ""
        self.summary = ""
        self.challenge_heading = ""
        self.capability_heading = ""
        self.outcome_heading = ""
        self.bullets = []
        self.chips = []
        self.outcomes = []
        self.next_steps = []

        # Internal state
        self._badge_done = False
        self._in_hero_title = False
        self._in_hero_tagline = False
        self._in_panel_heading = False
        self._in_bullet_li = False
        self._in_chip = False
        self._in_outcome_strong = False
        self._in_step_text = False
        self._buf = ""

    def _classes(self, attrs):
        for k, v in attrs:
            if k == "class":
                return (v or "").split()
        return []

    def handle_starttag(self, tag, attrs):
        classes = self._classes(attrs)

        if "badge" in classes and not self._badge_done:
            self._capture = "persona"
            self._buf = ""

        elif "hero-title" in classes:
            self._in_hero_title = True
            self._hero_title_buf = ""
            self._buf = ""

        elif "hero-tagline" in classes:
            self._in_hero_tagline = True
            self._buf = ""

        elif "panel-heading" in classes:
            self._in_panel_heading = True
            self._buf = ""

        elif "bullet-list" in classes:
            pass  # container, we capture li inside

        elif tag == "li" and self._in_bullet_list():
            self._in_bullet_li = True
            self._buf = ""

        elif "chip" in classes:
            self._in_chip = True
            self._buf = ""

        elif tag == "strong" and self._in_outcome_text():
            self._in_outcome_strong = True
            self._buf = ""

        elif "step-text" in classes:
            self._in_step_text = True
            self._buf = ""

        elif tag == "span" and self._in_hero_title:
            # tagline lives inside the <span> in hero-title
            self._in_span = True
            # project_name = what we've buffered so far (strip ": " suffix)
            raw = self._hero_title_buf.strip().rstrip(":")
            self.project_name = raw.strip()
            self._buf = ""

        self._stack.append((tag, classes))

    def _in_bullet_list(self):
        for _, cls in self._stack:
            if "bullet-list" in cls:
                return True
        return False

    def _in_outcome_text(self):
        for _, cls in self._stack:
            if "outcome-text" in cls:
                return True
        return False

    def handle_data(self, data):
        if self._capture == "persona":
            self._buf += data
        elif self._in_hero_title:
            if self._in_span:
                self._buf += data
            else:
                self._hero_title_buf += data
        elif self._in_hero_tagline:
            self._buf += data
        elif self._in_panel_heading:
            self._buf += data
        elif self._in_bullet_li:
            self._buf += data
        elif self._in_chip:
            self._buf += data
        elif self._in_outcome_strong:
            self._buf += data
        elif self._in_step_text:
            self._buf += data

    def handle_endtag(self, tag):
        if not self._stack:
            return
        # Pop matching tag from stack
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                _, classes = self._stack.pop(i)
                break
        else:
            return

        text = self._buf.strip()

        if self._capture == "persona" and "badge" in classes:
            self.persona = text
            self._badge_done = True
            self._capture = None
            self._buf = ""

        elif self._in_hero_title and tag == "span" and self._in_span:
            self.tagline = text
            self._in_span = False
            self._buf = ""

        elif self._in_hero_title and "hero-title" in classes:
            self._in_hero_title = False
            self._buf = ""

        elif self._in_hero_tagline and "hero-tagline" in classes:
            self.summary = text
            self._in_hero_tagline = False
            self._buf = ""

        elif self._in_panel_heading and "panel-heading" in classes:
            self._panel_heading_count += 1
            if self._panel_heading_count == 1:
                self.challenge_heading = text
            elif self._panel_heading_count == 2:
                self.capability_heading = text
            elif self._panel_heading_count == 3:
                self.outcome_heading = text
            self._in_panel_heading = False
            self._buf = ""

        elif self._in_bullet_li and tag == "li":
            if text:
                self.bullets.append(text)
            self._in_bullet_li = False
            self._buf = ""

        elif self._in_chip and "chip" in classes:
            if text:
                self.chips.append(text)
            self._in_chip = False
            self._buf = ""

        elif self._in_outcome_strong and tag == "strong":
            if text:
                self.outcomes.append(text)
            self._in_outcome_strong = False
            self._buf = ""

        elif self._in_step_text and "step-text" in classes:
            if text:
                self.next_steps.append(text)
            self._in_step_text = False
            self._buf = ""


def parse_slide(html):
    """Parse slide HTML, return dict of catalog fields (no slide_html, no urls)."""
    p = SlideParser()
    p.feed(html)
    return {
        "project_name": p.project_name,
        "persona":       p.persona,
        "tagline":       p.tagline,
        "summary":       p.summary,
        "chips":         p.chips,
        "bullets":       p.bullets,
        "outcomes":      p.outcomes,
        "next_steps":    p.next_steps,
        "challenge_heading":   p.challenge_heading,
        "capability_heading":  p.capability_heading,
        "outcome_heading":     p.outcome_heading,
    }


# ── Write catalog-data.js ─────────────────────────────────────────────────────

def write_catalog(items, output_path):
    lines = ["const DATA = ["]
    for i, item in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append(json.dumps(item, ensure_ascii=False) + comma)
    lines.append("];")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Wrote {output_path} ({os.path.getsize(output_path):,} bytes, {len(items)} items)")


# ── Git push ──────────────────────────────────────────────────────────────────

def git_push(repo_dir, count):
    cmds = [
        ["git", "-C", repo_dir, "add", "catalog-data.js"],
        ["git", "-C", repo_dir, "commit", "-m",
         f"chore: rebuild catalog-data.js ({count} items)"],
        ["git", "-C", repo_dir, "push", "origin", "gh-pages"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR: {' '.join(cmd)}\n  {result.stderr.strip()}")
            return False
        print(f"  {' '.join(cmd[2:])} — ok")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    push = "--push" in args
    org = next((args[i+1] for i, a in enumerate(args) if a == "--org"), ORG)
    token_arg = next((args[i+1] for i, a in enumerate(args) if a == "--token"), None)
    if token_arg:
        global GITHUB_TOKEN
        GITHUB_TOKEN = token_arg

    print(f"Org: {org}")
    print(f"Push: {push}")
    print(f"Auth: {'token' if GITHUB_TOKEN else 'unauthenticated (60 req/hr limit)'}")
    print()

    # 1. List repos
    print("Fetching repo list…")
    repos = list_repos(org)
    print(f"  Found {len(repos)} public repos")
    print()

    # 2. Process each repo
    items = []
    skipped = []

    for repo in sorted(repos):
        print(f"  [{repo}]", end=" ", flush=True)
        html, branch, raw_url = fetch_slide(org, repo)
        if not html:
            print("no slide")
            skipped.append(repo)
            continue

        fields = parse_slide(html)

        # Sanity check — skip if we got nothing useful
        if not fields["project_name"] and not fields["tagline"]:
            print("parse failed — skipping")
            skipped.append(repo)
            continue

        item = {
            "repo":      repo,
            "url":       f"https://github.com/{org}/{repo}/blob/{branch}/{SLIDE_FILE}",
            "raw_url":   raw_url,
            **fields,
            "slide_html": html,
        }
        items.append(item)
        chips_count = len(fields["chips"])
        print(f"ok  ({chips_count} chips, {len(fields['bullets'])} bullets, {len(fields['outcomes'])} outcomes)")

    print()
    print(f"Results: {len(items)} slides found, {len(skipped)} repos skipped")
    if skipped:
        print(f"  Skipped: {', '.join(skipped)}")
    print()

    if not items:
        print("Nothing to write. Exiting.")
        sys.exit(1)

    # 3. Write catalog-data.js
    if push:
        write_catalog(items, OUTPUT_FILE)
    else:
        # Dry run — write preview to /tmp so we don't clobber the real file
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "catalog-data-preview.js")
        write_catalog(items, tmp)
        print(f"  (dry run — actual file unchanged; preview at {tmp})")

    # 4. Update count badge in catalog.html (only when pushing)
    if not push:
        print("Dry run — pass --push to commit and deploy.")
        return
    catalog_html_path = os.path.join(os.path.dirname(OUTPUT_FILE), "catalog.html")
    if os.path.exists(catalog_html_path):
        html_src = open(catalog_html_path).read()
        updated = re.sub(
            r'(<div class="cat-sub">[^·]*·\s*)\d+( solutions</div>)',
            lambda m: f"{m.group(1)}{len(items)}{m.group(2)}",
            html_src
        )
        updated = re.sub(
            r'(<span class="count-badge"[^>]*>)\d+( solutions</span>)',
            lambda m: f"{m.group(1)}{len(items)}{m.group(2)}",
            updated
        )
        if updated != html_src:
            open(catalog_html_path, "w").write(updated)
            print(f"  Updated solution count to {len(items)} in catalog.html")

    # 5. Push
    print("Pushing to gh-pages…")
    repo_dir = os.path.dirname(OUTPUT_FILE)
    # Also stage catalog.html if it changed
    subprocess.run(["git", "-C", repo_dir, "add", "catalog.html"],
                   capture_output=True)
    git_push(repo_dir, len(items))


if __name__ == "__main__":
    main()
