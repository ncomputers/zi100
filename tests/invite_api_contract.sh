#!/usr/bin/env bash
set -euo pipefail

# Contract: POST /api/invites should return 201 and include inviteId in response
resp=$(curl -s -w "%{http_code}" -H 'Content-Type: application/json' \
  -d '{"inviteeEmail":"test@example.com","fullName":"Test User","roleId":1,"expiresAt":"2030-01-01T00:00:00.000Z"}' \
  -X POST http://localhost:5000/api/invites)

body=${resp::-3}
status=${resp: -3}
if [ "$status" != "201" ]; then
  echo "Expected 201 but got $status"
  exit 1
fi
echo "$body" | grep -q 'inviteId'
