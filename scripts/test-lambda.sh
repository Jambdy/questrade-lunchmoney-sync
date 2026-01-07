#!/bin/bash
# Script to manually invoke the Lambda function and check logs

FUNCTION_NAME="questrade-lunchmoney-sync"
REGION="us-east-1"
LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"

echo "=================================================="
echo "Testing Lambda Function: ${FUNCTION_NAME}"
echo "=================================================="
echo ""

# Invoke the function
echo "1. Invoking Lambda function..."
aws lambda invoke \
  --function-name ${FUNCTION_NAME} \
  --region ${REGION} \
  --cli-binary-format raw-in-base64-out \
  --payload '{}' \
  response.json

echo ""
echo "Response:"
cat response.json | jq '.'
echo ""

# Get the latest log stream
echo "2. Fetching latest logs..."
LATEST_STREAM=$(aws logs describe-log-streams \
  --log-group-name ${LOG_GROUP} \
  --region ${REGION} \
  --order-by LastEventTime \
  --descending \
  --max-items 1 \
  --query 'logStreams[0].logStreamName' \
  --output text)

echo "Latest log stream: ${LATEST_STREAM}"
echo ""

# Get log events
echo "3. Log output:"
echo "=================================================="
aws logs get-log-events \
  --log-group-name ${LOG_GROUP} \
  --log-stream-name "${LATEST_STREAM}" \
  --region ${REGION} \
  --query 'events[*].message' \
  --output text

echo "=================================================="
echo ""
echo "Test complete!"
