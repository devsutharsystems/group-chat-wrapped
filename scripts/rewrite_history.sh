#!/usr/bin/env bash
# One-time local history rewrite before publishing. NEVER run on a repository you have not rehearsed it on (see docs/PUBLISH.md). Never pushes.
#
#   scripts/rewrite_history.sh                                   # drop build/ and data/ (top-level only) from every commit
#   NEW_NAME='Name' NEW_EMAIL='address' scripts/rewrite_history.sh   # also rewrite author and committer (off by default; both variables are required)
#
# Refuses if a remote exists, the tree is dirty, HEAD is not on main, or any ref other than refs/heads/main exists.
# Uses git filter-branch (git-filter-repo is not installed on the development machine). No --prune-empty: the old and new commit counts stay 1:1 (asserted).
# Writes docs/results/commit_map.md (old hash, new hash, date, subject) BEFORE refs/original is deleted; it is left uncommitted for you to commit.
set -euo pipefail

die() { echo "rewrite_history: $*" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel)"

[ -z "$(git remote)" ] || die "a remote exists ($(git remote | tr '\n' ' ')); refusing to rewrite a repository that may have been pushed"
[ -z "$(git status --porcelain)" ] || die "the working tree is not clean"
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || die "HEAD is not on main"
others="$(git for-each-ref --format='%(refname)' | grep -vx 'refs/heads/main' || true)"
[ -z "$others" ] || die "refs other than main exist: $(echo "$others" | tr '\n' ' ')"
git ls-tree -r --name-only HEAD | grep -q '^src/gcw/data/' || die "src/gcw/data/ is not tracked at the tip (the packaged keyword file must exist)"
if [ -n "${NEW_NAME:-}${NEW_EMAIL:-}" ]; then
  [ -n "${NEW_NAME:-}" ] && [ -n "${NEW_EMAIL:-}" ] || die "set both NEW_NAME and NEW_EMAIL, or neither"
fi

OLD_COUNT="$(git rev-list --count main)"
git tag backup-pre-rewrite

ENVFILTER=""
if [ -n "${NEW_NAME:-}" ]; then
  export NEW_NAME NEW_EMAIL
  ENVFILTER='GIT_AUTHOR_NAME="$NEW_NAME"; GIT_AUTHOR_EMAIL="$NEW_EMAIL"; GIT_COMMITTER_NAME="$NEW_NAME"; GIT_COMMITTER_EMAIL="$NEW_EMAIL"; export GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL'
fi

# top-level paths only (root-anchored): `data` here is ./data, never src/gcw/data
export FILTER_BRANCH_SQUELCH_WARNING=1
if [ -n "$ENVFILTER" ]; then
  git filter-branch -f --env-filter "$ENVFILTER" --index-filter 'git rm -r --cached --ignore-unmatch -q -- build data' --tag-name-filter cat -- --all >/dev/null 2>&1
else
  git filter-branch -f --index-filter 'git rm -r --cached --ignore-unmatch -q -- build data' --tag-name-filter cat -- --all >/dev/null 2>&1
fi

NEW_COUNT="$(git rev-list --count main)"
[ "$OLD_COUNT" = "$NEW_COUNT" ] || die "commit count changed: $OLD_COUNT before, $NEW_COUNT after (empty commits are kept on purpose, so this must not happen)"
git ls-tree -r --name-only main | grep -q '^src/gcw/data/' || die "src/gcw/data/ was removed from the tip"
[ "$(git log main --name-only --pretty=format: | grep -cE '^(build|data)/' || true)" = "0" ] || die "build/ or data/ is still in history"
[ "$(git log main --name-only --pretty=format: | grep -c '^src/gcw/data/' || true)" -gt 0 ] || die "src/gcw/data/ is not in history any more"

# the commit map, BEFORE refs/original goes away: the n-th old commit (oldest first) is the n-th new commit
mkdir -p docs/results
{
  echo "# Commit map: history rewritten once before publishing"
  echo
  echo "Old and new hashes of every commit, oldest first. Removed from history: top-level build/ and data/. Commit count before and after: $OLD_COUNT and $NEW_COUNT (one to one)."
  [ -z "${NEW_NAME:-}" ] || echo "Author and committer were rewritten."
  echo
  echo "| old hash | new hash | date | subject |"
  echo "|---|---|---|---|"
  paste -d' ' <(git rev-list --reverse refs/original/refs/heads/main) <(git rev-list --reverse main) | while read -r old new; do
    printf '| %s | %s | %s | %s |\n' "$old" "$new" "$(git show -s --format=%as "$old")" "$(git show -s --format=%s "$old" | sed 's/|/\\|/g')"
  done
} > docs/results/commit_map.md

git tag -d backup-pre-rewrite >/dev/null
git for-each-ref --format='%(refname)' refs/original/ | while read -r r; do git update-ref -d "$r"; done
git reflog expire --expire=now --all
git gc --prune=now -q

[ "$(git for-each-ref --format='%(refname)')" = "refs/heads/main" ] || die "refs other than main remain after cleanup"
git checkout -q -f main
echo "rewrite_history: done. $NEW_COUNT commits (was $OLD_COUNT). docs/results/commit_map.md written, not committed. Nothing was pushed."
