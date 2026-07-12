#!/usr/bin/env bash
set -euo pipefail

JOB_ROOT="${JOB_ROOT:-/var/lib/neurotrust-ms/jobs}"
JOB_TTL_HOURS="${JOB_TTL_HOURS:-4}"

if [[ "$JOB_ROOT" != /var/lib/neurotrust-ms/jobs* ]]; then
  echo "Refusing to clean unexpected JOB_ROOT: $JOB_ROOT"
  exit 1
fi
if [[ ! -d "$JOB_ROOT" ]]; then
  echo "No job folder found at $JOB_ROOT"
  exit 0
fi

MINUTES=$(( JOB_TTL_HOURS * 60 ))
echo "Deleting NeuroTrust-MS job folders older than ${JOB_TTL_HOURS} hour(s) under $JOB_ROOT"
find "$JOB_ROOT" -mindepth 1 -maxdepth 1 -type d -mmin +"$MINUTES" -print -exec rm -rf {} +
