#!/usr/bin/env bash
# Test the hello-python zip skill against the deployed K8s agent.
#
# Usage:
#   ./test_hello_python_k8s.sh
#
# Required env vars (or edit the defaults below):
#   AGENT_URL   - Base URL of the deployed agent, e.g. https://agent.example.com
#   SKILL_URL   - Public URL of hello-python.zip, e.g. https://my-bucket.s3.amazonaws.com/skills/hello-python.zip
#
# To upload the zip to S3 first:
#   aws s3 cp examples/skills/hello-python.zip s3://YOUR_BUCKET/skills/hello-python.zip --profile YOUR_PROFILE
#   aws s3api put-object-acl --bucket YOUR_BUCKET --key skills/hello-python.zip --acl public-read --profile YOUR_PROFILE
#   # URL will be: https://YOUR_BUCKET.s3.amazonaws.com/skills/hello-python.zip

AGENT_URL="${AGENT_URL:-https://REPLACE_ME}"
SKILL_URL="${SKILL_URL:-https://REPLACE_ME/hello-python.zip}"

echo "Agent : $AGENT_URL"
echo "Skill : $SKILL_URL"
echo ""

curl -s -X POST "$AGENT_URL/api/chat" \
    -H "Content-Type: application/json" \
    -d "{
      \"messages\": [{
        \"role\": \"user\",
        \"content\": \"Run the hello world Python script\",
        \"platform_context\": {
          \"skills\": [{
            \"name\": \"hello-python\",
            \"version\": \"1.0.2\",
            \"url\": \"$SKILL_URL\"
          }]
        }
      }]
    }" | python -m json.tool
