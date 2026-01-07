# AWS Secrets Manager Integration

This application uses AWS Secrets Manager to automatically manage and rotate Questrade refresh tokens for multiple accounts, eliminating the need for manual updates every 7 days.

## How It Works

### The Problem
- Questrade refresh tokens expire after 7 days
- Managing multiple Questrade accounts requires tracking multiple tokens
- Each account needs to be linked to a specific Lunch Money asset
- Manually updating this configuration is tedious and error-prone

### The Solution
1. **Initial Setup**: Store all Questrade account configurations in a single AWS Secrets Manager secret
2. **Each Lambda Run**:
   - Read the current account configurations from Secrets Manager
   - For each account:
     - Use the refresh token to authenticate with Questrade
     - Look up the corresponding Lunch Money asset by name
     - Sync transactions to the correct asset
     - Questrade returns a new refresh token (extends validity by 7 days)
   - Automatically update Secrets Manager with all new tokens
3. **Result**: As long as the Lambda runs at least once every 7 days, tokens never expire!

## Setup Instructions

### Option 1: Using the Setup Script (Recommended)

1. **Ensure Lunch Money Assets Exist**:
   - Log into Lunch Money
   - Create manual assets (Settings → Assets → Add Asset → Manual)
   - Name them exactly:
     - `Questrade - James - RRSP`
     - `Questrade - Christine - RRSP`

2. **Run the setup script**:
   ```bash
   ./scripts/create-secret.sh
   ```

   This will create or update the AWS Secrets Manager secret with your account configurations.

3. **Deploy with SAM**:
   ```bash
   sam deploy \
     --parameter-overrides \
       QuestradeRefreshTokens="" \
       LunchMoneyApiToken="your_lunchmoney_api_token" \
       UseSecretsManager="true"
   ```

   Note: Leave `QuestradeRefreshTokens` empty since we're using Secrets Manager.

4. **Done!** No manual token updates needed ever again.

### Option 2: Manual AWS CLI Setup

1. **Ensure Lunch Money Assets Exist** (as above)

2. **Create the secret manually**:
   ```bash
   aws secretsmanager create-secret \
     --name questrade-lunchmoney/account-configs \
     --secret-string '{
       "accounts": [
         {
           "questrade_account_id": "53219675",
           "questrade_refresh_token": "d6TLCxGgMzGIza6q-W3wCDzL4Ybah0oH0",
           "lunchmoney_asset_name": "Questrade - James - RRSP"
         },
         {
           "questrade_account_id": "53230366",
           "questrade_refresh_token": "nqU9H1lPMU_D2EHtCPlemEpPwLg8UK-i0",
           "lunchmoney_asset_name": "Questrade - Christine - RRSP"
         }
       ]
     }' \
     --region us-east-1
   ```

   **Format:** JSON with an `accounts` array, where each account has:
   - `questrade_account_id`: Your Questrade account number
   - `questrade_refresh_token`: OAuth refresh token from Questrade
   - `lunchmoney_asset_name`: Exact name of the asset in Lunch Money

3. **Deploy with SAM** (as above)

## Configuration

### Environment Variables

The Lambda function uses these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_SECRETS_MANAGER` | `true` | Enable/disable Secrets Manager |
| `QUESTRADE_SECRET_NAME` | `questrade-lunchmoney/account-configs` | Secret name in Secrets Manager |
| `LUNCHMONEY_API_TOKEN` | (required) | Lunch Money API token (doesn't rotate) |
| `SYNC_DAYS_BACK` | `31` | Number of days to sync (max 31) |

**Note:** Account configurations (including tokens and asset mappings) are stored in Secrets Manager.

### SAM Template Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `QuestradeRefreshTokens` | `""` | Initial account configs JSON (only for first deployment) |
| `QuestradeSecretName` | `questrade-lunchmoney/account-configs` | Secret name |
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

### Check Current Configuration

View the current account configurations in Secrets Manager:

```bash
aws secretsmanager get-secret-value \
  --secret-id questrade-lunchmoney/account-configs \
  --region us-east-1 \
  --query 'SecretString' \
  --output text | jq .
```

### Lambda Response

When Lambda runs successfully, the response includes:

```json
{
  "statusCode": 200,
  "body": {
    "message": "Sync completed successfully",
    "accounts_processed": 2,
    "tokens_rotated": 2,
    "configs_auto_updated": true,
    "using_secrets_manager": true,
    "totals": {
      "new_transactions": 15,
      "skipped_duplicates": 3
    }
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
2. Set `QUESTRADE_ACCOUNT_CONFIGS` as an environment variable with the JSON configuration
3. Manually update the tokens every 7 days

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
1. Run `./scripts/create-secret.sh` to create the secret
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

### Error: "Lunch Money asset not found"

**Cause**: The asset name in the configuration doesn't match any asset in Lunch Money.

**Solutions**:
1. Check the exact asset name in Lunch Money (case-sensitive)
2. Create the asset in Lunch Money if it doesn't exist
3. Update the secret with the correct asset name:
   ```bash
   ./scripts/create-secret.sh
   ```

## Migration from Environment Variables

If you're currently using environment variables:

1. **Get your current configuration** from the Lambda environment variables
2. **Create the secret** with the new format:
   ```bash
   ./scripts/create-secret.sh
   ```
3. **Update deployment** to use Secrets Manager (set `USE_SECRETS_MANAGER=true`)
4. **Remove** old environment variables (optional, acts as fallback)

## Additional Resources

- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)
- [Questrade API Documentation](https://www.questrade.com/api/documentation)
- [Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
