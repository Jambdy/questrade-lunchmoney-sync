#!/bin/bash
aws cloudformation delete-stack --stack-name questrade-lunchmoney-sync --region us-east-1
echo "Waiting for stack deletion to complete..."
aws cloudformation wait stack-delete-complete --stack-name questrade-lunchmoney-sync --region us-east-1 || true
echo "Stack deleted successfully"
