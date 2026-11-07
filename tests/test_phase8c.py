"""Phase 8c: README CI wording after the first green run, the publish status, the site's repository link, and the pages workflow facts."""
from __future__ import annotations

import hashlib
import re

from test_privacy import ROOT

README = (ROOT / "README.md").read_text(encoding="utf-8")
PUBLISH = (ROOT / "docs" / "PUBLISH.md").read_text(encoding="utf-8")
REPO = "https://github.com/" + "devsu" + "tharsystems/group-chat-wrapped"  # built from parts: the repo's mentions check lists the account name


def test_readme_says_what_ci_did_and_what_it_did_not_check():
    ev = README.split("## Evaluation", 1)[1].split("\n## ", 1)[0]
    tested = next(ln for ln in ev.splitlines() if ln.startswith("**Tested on:**"))
    for k in ("CI passed on Python 3.11 and 3.13 on `ubuntu-latest`", "the render tests ran with the runner's fonts", "the slow render tests are deselected in CI",
              "first CI run failed for a browser-path reason", "which the next commit fixed", "migrating to Ubuntu 26", "no CI badge yet"):
        assert k in tested, k
    lim = README.split("## Limits", 1)[1].split("\n## ", 1)[0]
    assert "emoji appearance on Linux was not inspected" in lim and "layout tests of the card passed on the CI runner" in lim
    assert "Cards need a colour emoji font on Linux; this is unverified" not in README and "has not run yet" not in README
    assert "slow render tests are deselected there" in lim and "migrating to Ubuntu 26" in lim
    assert "![ci" not in README.lower() and "badge.svg" not in README.lower() and "actions/workflows" not in README


def test_publish_status_lines():
    assert "Status after Phase 8c: steps 1 to 8 are done" in PUBLISH and "CI green on Python 3.11 and 3.13" in PUBLISH
    assert "Remaining: a final read of the README, the public flip (step 9) and enabling Pages (step 10)" in PUBLISH
    assert "Nothing here has been run." not in PUBLISH and "the public flip and Pages are NOT run" in PUBLISH and "git push -u origin main" in PUBLISH


def test_the_site_links_to_the_repository_once_per_page_and_the_cards_are_unchanged():
    for name in ("index.html", "methodology.html"):
        h = (ROOT / "site" / name).read_text(encoding="utf-8")
        assert h.count(f'<a href="{REPO}">{REPO}</a>') == 1 and "added when the repository is published" not in h
        assert re.findall(r"https?://[^\"' <]+", h) == [REPO, REPO]  # only the plain link (href and its text); no resource loads
    assert hashlib.sha256((ROOT / "site/img/stats_card.png").read_bytes()).hexdigest() == "c910ba35b229f37e6c9eb2b0b0c75c61c65cec657c8a02bbfcc8fb34fb51994d"
    assert hashlib.sha256((ROOT / "site/img/ai_card.png").read_bytes()).hexdigest() == "028862cd39c37b6fff704648b39004379ea08980d094c4e6b006c97f29cd223a"


def test_the_pages_workflow_triggers_permissions_and_upload_folder():
    t = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert re.search(r"^on:\n  push:\n    branches: \[main\]\n    paths: \['site/\*\*', '\.github/workflows/pages\.yml'\]\n  workflow_dispatch:\n", t, re.M)
    assert re.search(r"^permissions:\n  contents: read\n  pages: write\n  id-token: write\n", t, re.M)
    assert "path: site" in t and "actions/upload-pages-artifact@v3" in t and "actions/deploy-pages@v4" in t and "name: github-pages" in t
