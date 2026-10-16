#!/bin/sh
# Import the versioned workflows into n8n and publish them. Runs inside the n8n
# container (see docs/notifications.md); n8n has to be restarted afterwards to
# register the webhooks of what was published.
#
# Importing replaces a workflow with the same ID, so this also brings n8n back
# in line with the repository after a change. Credentials are linked by name,
# so create them first.
set -e

n8n import:workflow --separate --input=/automation/workflows

# n8n in regular mode cannot activate workflows on import, so each one is
# published on its own. The error workflow goes first, since the other two
# point to it.
for id in quetzalNotifyErr quetzalDigest001 quetzalFailure01; do
    n8n publish:workflow --id="$id"
done
