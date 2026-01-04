# Deployment Guide

This guide covers deploying the Questrade to Lunch Money sync application using AWS SAM (Serverless Application Model).

> **🚀 Quick Start with GitHub Actions**: For automated CI/CD deployment, see [GITHUB_ACTIONS.md](GITHUB_ACTIONS.md)

## Deployment Methods

You can deploy this application using:
1. **[GitHub Actions](GITHUB_ACTIONS.md)** (Recommended) - Automated CI/CD with secrets management
2. **Manual SAM CLI** (This guide) - Local deployment for development/testing

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured
   ```bash
   aws configure
   ```
3. **AWS SAM CLI** installed
   - Install: [AWS SAM CLI Installation Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
   - Verify: `sam --version`

4. **Python 3.11** or later
5. **API Credentials**:
   - Questrade refresh token
   - Lunch Money API token
   - Questrade account IDs

## Project Structure

```
questrade-lunchmoney-sync/
├── src/
│   ├── __init__.py
│   ├── questrade.py          # Questrade API client
│   ├── lunchmoney.py         # Lunch Money API client
│   ├── sync.py               # Sync logic
│   └── lambda_handler.py     # Lambda entry point
├── tests/
│   └── test_sync.py
├── template.yaml             # SAM CloudFormation template
├── samconfig.toml           # SAM CLI configuration
├── requirements.txt         # Python dependencies
├── .env.example            # Environment variable template
└── DEPLOYMENT.md           # This file
```

## Deployment Steps

### 1. Install Dependencies Locally (for testing)

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

For local testing, create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your actual credentials:
```bash
QUESTRADE_REFRESH_TOKEN=your_refresh_token
LUNCHMONEY_API_TOKEN=your_api_token
QUESTRADE_ACCOUNT_IDS=123456,789012
SYNC_DAYS_BACK=31
LUNCHMONEY_ASSET_ID=  # Optional
```

### 3. Test Locally

```bash
# Run the handler locally
python -m src.lambda_handler

# Or run tests
python -m pytest tests/
```

### 4. Validate SAM Template

```bash
sam validate
```

### 5. Build the Application

```bash
sam build
```

This will:
- Create a `.aws-sam/` directory
- Install dependencies
- Package your code

### 6. Deploy to AWS

#### Option A: Guided Deployment (First Time)

```bash
sam deploy --guided
```

You'll be prompted for:
- **Stack Name**: `questrade-lunchmoney-sync` (default)
- **AWS Region**: `us-east-1` (or your preferred region)
- **Parameter QuestradeRefreshToken**: Your Questrade refresh token
- **Parameter LunchMoneyApiToken**: Your Lunch Money API token
- **Parameter QuestradeAccountIds**: Comma-separated account IDs
- **Parameter SyncDaysBack**: Number of days (1-31, default: 31)
- **Parameter LunchMoneyAssetId**: Optional asset ID (leave empty if not needed)
- **Parameter SyncSchedule**: Cron expression (default: `cron(0 8 * * ? *)` = daily at 8 AM UTC)
- **Parameter LogRetentionDays**: Log retention (default: 30 days)
- **Confirm changes before deploy**: Y
- **Allow SAM CLI IAM role creation**: Y
- **Save arguments to samconfig.toml**: Y

#### Option B: Deploy with Parameters File

Create `parameters.json`:
```json
{
  "Parameters": {
    "QuestradeRefreshToken": "your_token",
    "LunchMoneyApiToken": "your_token",
    "QuestradeAccountIds": "123456,789012",
    "SyncDaysBack": "31",
    "LunchMoneyAssetId": "",
    "SyncSchedule": "cron(0 8 * * ? *)",
    "LogRetentionDays": "30"
  }
}
```

Then deploy:
```bash
sam deploy --parameter-overrides $(cat parameters.json | jq -r '.Parameters | to_entries | map("\(.key)=\(.value)") | join(" ")')
```

#### Option C: Deploy with Inline Parameters

```bash
sam deploy \
  --parameter-overrides \
    QuestradeRefreshToken=your_token \
    LunchMoneyApiToken=your_token \
    QuestradeAccountIds=123456,789012 \
    SyncDaysBack=31 \
    LunchMoneyAssetId= \
    "SyncSchedule=cron(0 8 * * ? *)" \
    LogRetentionDays=30
```

### 7. Verify Deployment

Check the stack status:
```bash
aws cloudformation describe-stacks \
  --stack-name questrade-lunchmoney-sync \
  --query 'Stacks[0].StackStatus'
```

List stack outputs:
```bash
sam list stack-outputs
```

## Post-Deployment

### Subscribe to Error Notifications

Get the SNS topic ARN:
```bash
aws cloudformation describe-stacks \
  --stack-name questrade-lunchmoney-sync \
  --query 'Stacks[0].Outputs[?OutputKey==`ErrorNotificationTopicArn`].OutputValue' \
  --output text
```

Subscribe with your email:
```bash
aws sns subscribe \
  --topic-arn <TOPIC_ARN_FROM_ABOVE> \
  --protocol email \
  --notification-endpoint your-email@example.com
```

Confirm the subscription via the email you receive.

### View Logs

```bash
# Using SAM CLI
sam logs --tail

# Using AWS CLI
aws logs tail /aws/lambda/questrade-lunchmoney-sync --follow
```

### Invoke Manually

Test the function manually:
```bash
sam local invoke SyncFunction
```

Or invoke in AWS:
```bash
aws lambda invoke \
  --function-name questrade-lunchmoney-sync \
  --cli-binary-format raw-in-base64-out \
  --payload '{}' \
  response.json

cat response.json
```

## Updating the Application

### Update Code

1. Make changes to your code
2. Rebuild:
   ```bash
   sam build
   ```
3. Deploy:
   ```bash
   sam deploy
   ```

### Update Parameters

To update environment variables or schedule:
```bash
sam deploy \
  --parameter-overrides \
    QuestradeRefreshToken=new_token \
    SyncSchedule="cron(0 12 * * ? *)"
```

### Update Questrade Refresh Token

The Questrade refresh token gets updated after each use. Check the Lambda logs for the new token:

```bash
aws logs tail /aws/lambda/questrade-lunchmoney-sync --since 1h | grep "new refresh token"
```

Then update the Lambda environment variable:
```bash
aws lambda update-function-configuration \
  --function-name questrade-lunchmoney-sync \
  --environment "Variables={QUESTRADE_REFRESH_TOKEN=new_token,LUNCHMONEY_API_TOKEN=your_token,QUESTRADE_ACCOUNT_IDS=123456,SYNC_DAYS_BACK=31}"
```

## Monitoring

### CloudWatch Dashboard

Create a custom dashboard to monitor:
- Function invocations
- Errors
- Duration
- Log insights

### CloudWatch Alarms

The template includes two alarms:
1. **Error Alarm**: Triggers when the function errors
2. **Duration Alarm**: Triggers when execution time is too long

### Metrics to Monitor

- `Invocations`: Number of times the function is invoked
- `Errors`: Number of failed invocations
- `Duration`: Execution time
- `Throttles`: Number of throttled invocations

## Cleanup

To delete the stack and all resources:

```bash
sam delete
```

Or:
```bash
aws cloudformation delete-stack --stack-name questrade-lunchmoney-sync
```

## Troubleshooting

### Build Fails

**Issue**: Dependencies won't install
```bash
# Try building in a container (ensures Linux compatibility)
sam build --use-container
```

### Deployment Fails

**Issue**: Permission denied
- Ensure your AWS credentials have sufficient permissions
- Required permissions: Lambda, CloudFormation, IAM, CloudWatch, EventBridge, S3

**Issue**: Stack already exists
```bash
# Update existing stack
sam deploy --no-confirm-changeset
```

### Function Errors

**Check logs**:
```bash
sam logs --tail --stack-name questrade-lunchmoney-sync
```

**Common issues**:
1. Invalid Questrade refresh token → Get a new one from Questrade
2. Invalid Lunch Money API token → Check your token in Lunch Money settings
3. Invalid account IDs → Verify account IDs via Questrade API
4. API rate limits → Reduce sync frequency

### Testing Issues

**Issue**: Import errors when running locally
```bash
# Make sure you're in the project root
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python -m src.lambda_handler
```

## Cost Optimization

### Estimated Monthly Costs

Based on daily sync (30 invocations/month):
- **Lambda**: ~$0.20/month
  - 128MB memory, 10-second average duration
- **CloudWatch Logs**: ~$0.50/month
  - 30-day retention
- **CloudWatch Alarms**: ~$0.20/month
  - 2 alarms
- **SNS**: Free tier
- **EventBridge**: Free

**Total**: ~$0.90/month

### Cost Reduction Tips

1. Reduce log retention:
   ```bash
   sam deploy --parameter-overrides LogRetentionDays=7
   ```

2. Reduce memory (if function doesn't need it):
   Edit `template.yaml` → `Globals.Function.MemorySize: 128`

3. Less frequent sync:
   ```bash
   sam deploy --parameter-overrides SyncSchedule="cron(0 8 * * 1 *)"  # Weekly on Mondays
   ```

## Security Best Practices

### Use AWS Secrets Manager (Recommended)

Instead of storing tokens in environment variables, use Secrets Manager:

1. Create secrets:
   ```bash
   aws secretsmanager create-secret \
     --name questrade-lunchmoney/questrade-token \
     --secret-string "your_questrade_token"

   aws secretsmanager create-secret \
     --name questrade-lunchmoney/lunchmoney-token \
     --secret-string "your_lunchmoney_token"
   ```

2. Update Lambda to read from Secrets Manager (requires code changes)

3. Add Secrets Manager permissions to the Lambda role

### Use Parameter Store (Alternative)

Store sensitive values in AWS Systems Manager Parameter Store:
```bash
aws ssm put-parameter \
  --name /questrade-lunchmoney/questrade-token \
  --value "your_token" \
  --type SecureString
```

## Advanced Configuration

### Custom VPC

If you need to run the Lambda in a VPC (for network restrictions):

Add to `template.yaml` under `SyncFunction.Properties`:
```yaml
VpcConfig:
  SecurityGroupIds:
    - sg-12345678
  SubnetIds:
    - subnet-12345678
    - subnet-87654321
```

### Dead Letter Queue

Add a DLQ for failed executions:

```yaml
DeadLetterQueue:
  Type: SQS
  TargetArn: !GetAtt SyncFunctionDLQ.Arn
```

### Reserved Concurrency

Limit concurrent executions:
```yaml
ReservedConcurrentExecutions: 1
```

## Support

For issues or questions:
1. Check CloudWatch logs
2. Review this deployment guide
3. Check the main [README.md](README.md)
4. Open an issue on GitHub

## Additional Resources

- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Questrade API Documentation](https://www.questrade.com/api/documentation)
- [Lunch Money API Documentation](https://lunchmoney.dev/)
