#!/bin/sh
# Fails when this checkout breaks a gold contract of an earlier commit: a
# column removed, renamed or given another type, a not-null constraint
# dropped, or a contract no longer enforced. Adding a column does not break
# a contract. Run it from transform/, with dbt on the PATH:
#
#     uv run sh check-contract-changes.sh <commit>
#
# dbt finds breaking changes by comparing two manifests, so the dbt project
# of that commit is parsed in a separate worktree first. A change meant to
# break a contract goes into a new version of the model instead, and the
# old version stays until its consumers have moved.
set -eu

base="$1"
work=$(mktemp -d)
cleanup() {
    git worktree remove --force "$work/base" > /dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT

git worktree add --quiet --detach "$work/base" "$base"
if [ ! -f "$work/base/transform/dbt_project.yml" ]; then
    echo "No dbt project at $base; nothing to compare."
    exit 0
fi
(
    cd "$work/base/transform"
    dbt deps --quiet
    dbt parse --quiet --target-path "$work/state"
)

# For a model without versions dbt only warns about a breaking change; here
# it is an error, so the check fails. It lists the models changed since.
echo "Models changed since $base:"
dbt --warn-error-options '{"error": ["UnversionedBreakingChange"]}' \
    ls --quiet --resource-type model --select state:modified --state "$work/state"
echo "No gold contract of $base is broken."
