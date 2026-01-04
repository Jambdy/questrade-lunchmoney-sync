# AWS Secrets Manager Integration

This application uses AWS Secrets Manager to automatically manage and rotate the Questrade refresh token, eliminating the need for manual updates every 7 days.

## How It Works

### The Problem
Questrade refresh tokens expire after 7 days. Manually updating them is tedious and error-prone.

### The Solution
1. **Initial Setup**: Store the Questrade refresh token in AWS Secrets Manager
2. **Each Lambda Run**:
   - Read the current token from Secrets Manager
   - Use it to authenticate with Questrade
   - Questrade returns a new refresh token (extends validity by 7 days)
   - Automatically update Secrets Manager with the new token
3. **Result**: As long as the Lambda runs at least once every 7 days, the token never expires!

## Setup Instructions

### Option 1: Using GitHub Actions (Recommended)

1. **Add GitHub Secrets**:
   - Go to your repo → Settings → Secrets and variables → Actions
   - Add these secrets:
     ```
     QUESTRADE_REFRESH_TOKEN=xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0
     LUNCHMONEY_API_TOKEN=your_lunch_money_token
     QUESTRADE_ACCOUNT_IDS=12345678,87654321
     ```

2. **Push to GitHub**:
   ```bash
   git push origin master
   ```

3. **GitHub Actions will**:
   - Check if Secrets Manager secret exists
   - If not, create it with your `QUESTRADE_REFRESH_TOKEN`
   - Deploy the Lambda function
   - Lambda will automatically update the secret on each run

4. **Done!** No manual token updates needed ever again.

### Option 2: Manual SAM Deployment

1. **Create the secret manually** (first time only):
   ```bash
   aws secretsmanager create-secret \
     --name questrade-lunchmoney/questrade-token \
     --secret-string "xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0" \
     --region us-east-1
   ```

2. **Deploy with SAM**:
   ```bash
   sam deploy \
     --parameter-overrides \
       QuestradeRefreshToken="" \
       LunchMoneyApiToken="your_token" \
       QuestradeAccountIds="12345678" \
       UseSecretsManager="true"
   ```

   Note: Leave `QuestradeRefreshToken` empty since we're using Secrets Manager.

## Configuration

### Environment Variables

The Lambda function uses these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_SECRETS_MANAGER` | `true` | Enable/disable Secrets Manager |
| `QUESTRADE_SECRET_NAME` | `questrade-lunchmoney/questrade-token` | Secret name in Secrets Manager |
| `LUNCHMONEY_API_TOKEN` | (required) | Lunch Money API token (doesn't rotate) |
| `QUESTRADE_ACCOUNT_IDS` | (required) | Comma-separated account IDs |

### SAM Template Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `QuestradeRefreshToken` | `""` | Initial token (only for first deployment) |
| `QuestradeSecretName` | `questrade-lunchmoney/questrade-token` | Secret name |
| `UseSecretsManager` | `true` | Enable Secrets Manager |

## Token Lifecycle

```
Day 0: Initial token (valid for 7 days)
  ↓
Day 1: Lambda runs → Gets new token (valid for 7 days) → Updates Secrets Manager
  ↓
Day 2: Lambda runs → Gets new token (valid for 7 days) → Updates Secrets Manager
  ↓
...continues forever as long as Lambda runs weekly
```

## Monitoring

### Check if Token Updated

View CloudWatch Logs for your Lambda function:

```bash
aws logs tail /aws/lambda/questrade-lunchmoney-sync --follow
```

Look for log messages:
- ✅ `Successfully updated Questrade refresh token in Secrets Manager`
- ❌ `Failed to update Questrade refresh token in Secrets Manager`

### Check Current Token

View the current token in Secrets Manager:

```bash
aws secretsmanager get-secret-value \
  --secret-id questrade-lunchmoney/questrade-token \
  --region us-east-1 \
  --query 'SecretString' \
  --output text
```

### Lambda Response

When Lambda runs successfully, the response includes:

```json
{
  "statusCode": 200,
  "body": {
    "message": "Sync completed successfully",
    "token_rotated": true,
    "token_auto_updated": true,
    "using_secrets_manager": true
  }
}
```

## Costs

- **Secrets Manager**: $0.40/month per secret
- **API calls**: ~$0.05/month (2 calls per Lambda run, daily runs)
- **Total**: ~$0.45-0.50/month

## Fallback to Environment Variables

If you prefer not to use Secrets Manager:

1. Set `USE_SECRETS_MANAGER=false` in your deployment
2. Set `QUESTRADE_REFRESH_TOKEN` as an environment variable
3. Manually update the token every 7 days

## Troubleshooting

### Error: "Access denied to secret"

**Cause**: Lambda doesn't have permission to access Secrets Manager.

**Solution**: Verify the Lambda execution role has these permissions:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue",
    "secretsmanager:PutSecretValue",
    "secretsmanager:UpdateSecret"
  ],
  "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:questrade-lunchmoney/*"
}
```

The SAM template automatically adds these permissions.

### Error: "Secret not found"

**Cause**: The secret doesn't exist in Secrets Manager.

**Solutions**:
1. **GitHub Actions**: Add `QUESTRADE_REFRESH_TOKEN` secret and redeploy
2. **Manual**: Create the secret manually (see Setup instructions)

### Token Not Updating

**Check**:
1. Lambda logs for error messages
2. Lambda has Secrets Manager permissions
3. `USE_SECRETS_MANAGER` environment variable is `true`
4. Secret name matches `QUESTRADE_SECRET_NAME`

## Security Best Practices

✅ **Do**:
- Use Secrets Manager for automatic rotation
- Enable CloudWatch Logs encryption
- Use least-privilege IAM policies
- Monitor CloudWatch Logs for errors

❌ **Don't**:
- Store tokens in environment variables for production
- Share or commit tokens to version control
- Disable Secrets Manager without a good reason
- Skip monitoring logs

## Migration from Environment Variables

If you're currently using environment variables:

1. **Get your current token** from the Lambda environment variables
2. **Create the secret**:
   ```bash
   aws secretsmanager create-secret \
     --name questrade-lunchmoney/questrade-token \
     --secret-string "YOUR_CURRENT_TOKEN"
   ```
3. **Update deployment** to use Secrets Manager (set `USE_SECRETS_MANAGER=true`)
4. **Remove** `QUESTRADE_REFRESH_TOKEN` environment variable (optional, acts as fallback)

## Additional Resources

- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)
- [Questrade API Documentation](https://www.questrade.com/api/documentation)
- [Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
