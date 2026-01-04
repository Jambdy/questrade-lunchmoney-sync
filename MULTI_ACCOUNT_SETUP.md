# Multiple Questrade Accounts Setup

This guide explains how to sync multiple Questrade accounts (e.g., yours and your spouse's) to Lunch Money.

## Why Multiple Accounts?

Each Questrade login requires its own OAuth refresh token. If you have:
- Your personal Questrade account
- Your spouse's Questrade account

You need separate tokens for each since they authenticate different users.

## Configuration Format

### GitHub Secrets (Recommended)

Set up these secrets in your GitHub repository:

#### Tokens
| Secret Name | Description | Example |
|------------|-------------|---------|
| `QUESTRADE_REFRESH_TOKEN_PRIMARY` | Your Questrade refresh token | `xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0` |
| `QUESTRADE_REFRESH_TOKEN_SPOUSE` | Spouse's Questrade refresh token | `yBDuQHD-CPFwn8LiiH1pJwj-SPIeLBht1` |

#### Account IDs
| Secret Name | Description | Example |
|------------|-------------|---------|
| `QUESTRADE_ACCOUNT_IDS_PRIMARY` | Your account IDs (comma-separated) | `12345678,12345679` |
| `QUESTRADE_ACCOUNT_IDS_SPOUSE` | Spouse's account IDs (comma-separated) | `87654321` |

The workflow will automatically build the configuration JSON from these secrets.

### Environment Variables (Local/Manual)

If deploying manually or testing locally, use these formats:

#### QUESTRADE_ACCOUNTS
```json
{
  "primary": {
    "account_ids": ["12345678", "12345679"],
    "token_key": "primary"
  },
  "spouse": {
    "account_ids": ["87654321"],
    "token_key": "spouse"
  }
}
```

#### QUESTRADE_REFRESH_TOKEN (or Secrets Manager)
```json
{
  "primary": "xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0",
  "spouse": "yBDuQHD-CPFwn8LiiH1pJwj-SPIeLBht1"
}
```

## How It Works

1. **Initial Setup**:
   - Primary account: Token stored as `primary` key
   - Spouse account: Token stored as `spouse` key

2. **Each Lambda Run**:
   - Reads both tokens from Secrets Manager
   - Syncs primary account(s) with primary token
   - Syncs spouse account(s) with spouse token
   - Updates both tokens in Secrets Manager if they changed

3. **Result**:
   - Both accounts stay authenticated
   - Tokens automatically rotate
   - All transactions appear in Lunch Money

## Getting Your Tokens

### Primary Account

1. Log into **your** Questrade account
2. Go to Account Management → API Access
3. Create app: "Lunch Money Sync - Primary"
4. Generate refresh token
5. Copy token immediately (shown only once)
6. Save as `QUESTRADE_REFRESH_TOKEN_PRIMARY`

### Spouse Account

1. Log into **spouse's** Questrade account
2. Go to Account Management → API Access
3. Create app: "Lunch Money Sync - Spouse"
4. Generate refresh token
5. Copy token immediately
6. Save as `QUESTRADE_REFRESH_TOKEN_SPOUSE`

## Getting Account IDs

### Option 1: Via Questrade Website
1. Log into Questrade
2. View your accounts
3. Account number is displayed (usually 8 digits)

### Option 2: Via API (Advanced)
```bash
# Use your refresh token to get account IDs
curl "https://login.questrade.com/oauth2/token?grant_type=refresh_token&refresh_token=YOUR_TOKEN"
# Use the api_server and access_token from response
curl "API_SERVER/v1/accounts" -H "Authorization: Bearer ACCESS_TOKEN"
```

## Example GitHub Secrets Setup

For a couple with accounts:
- Primary: 2 TFSA accounts (12345678, 12345679)
- Spouse: 1 RRSP account (87654321)

```
QUESTRADE_REFRESH_TOKEN_PRIMARY=xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0
QUESTRADE_REFRESH_TOKEN_SPOUSE=yBDuQHD-CPFwn8LiiH1pJwj-SPIeLBht1
QUESTRADE_ACCOUNT_IDS_PRIMARY=12345678,12345679
QUESTRADE_ACCOUNT_IDS_SPOUSE=87654321
LUNCHMONEY_API_TOKEN=your_lunchmoney_token_here
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

## Secrets Manager Format

After first deployment, Secrets Manager will contain:

**Secret Name**: `questrade-lunchmoney/questrade-tokens`

**Secret Value** (JSON):
```json
{
  "primary": "xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0",
  "spouse": "yBDuQHD-CPFwn8LiiH1pJwj-SPIeLBht1"
}
```

This JSON is automatically maintained - both tokens update independently as they rotate.

## Monitoring

### CloudWatch Logs

Look for log entries like:
```
Starting sync for 2 Questrade account group(s)
Processing primary: 2 account(s)
  Account primary:12345678: 5 new, 2 skipped
  Account primary:12345679: 3 new, 1 skipped
Processing spouse: 1 account(s)
  Account spouse:87654321: 2 new, 0 skipped
2 Questrade token(s) updated
✅ Successfully updated Questrade refresh tokens in Secrets Manager
  - Updated token for: primary
  - Updated token for: spouse
```

### Lambda Response

```json
{
  "statusCode": 200,
  "body": {
    "message": "Sync completed successfully",
    "results": {
      "primary:12345678": {"new_transactions": 5, "skipped_duplicates": 2},
      "primary:12345679": {"new_transactions": 3, "skipped_duplicates": 1},
      "spouse:87654321": {"new_transactions": 2, "skipped_duplicates": 0}
    },
    "totals": {
      "new_transactions": 10,
      "skipped_duplicates": 3
    },
    "accounts_processed": 2,
    "tokens_rotated": 2,
    "tokens_auto_updated": true
  }
}
```

## Adding More Accounts

To add a third account (e.g., child's account):

1. **Get new token** from child's Questrade account
2. **Add GitHub secrets**:
   - `QUESTRADE_REFRESH_TOKEN_CHILD`
   - `QUESTRADE_ACCOUNT_IDS_CHILD`

3. **Update workflow** (`.github/workflows/deploy.yml`):
   ```yaml
   TOKENS_JSON=$(jq -n \
     --arg primary "${{ secrets.QUESTRADE_REFRESH_TOKEN_PRIMARY }}" \
     --arg spouse "${{ secrets.QUESTRADE_REFRESH_TOKEN_SPOUSE }}" \
     --arg child "${{ secrets.QUESTRADE_REFRESH_TOKEN_CHILD }}" \
     '{primary: $primary, spouse: $spouse, child: $child}')

   ACCOUNTS_JSON=$(jq -n \
     --arg primary_ids "${{ secrets.QUESTRADE_ACCOUNT_IDS_PRIMARY }}" \
     --arg spouse_ids "${{ secrets.QUESTRADE_ACCOUNT_IDS_SPOUSE }}" \
     --arg child_ids "${{ secrets.QUESTRADE_ACCOUNT_IDS_CHILD }}" \
     '{
       primary: {account_ids: ($primary_ids | split(",")), token_key: "primary"},
       spouse: {account_ids: ($spouse_ids | split(",")), token_key: "spouse"},
       child: {account_ids: ($child_ids | split(",")), token_key: "child"}
     }')
   ```

4. **Redeploy** - tokens will be added to Secrets Manager

## Troubleshooting

### Only One Account Syncing

**Check**:
- Both token secrets are set in GitHub
- Both account ID secrets are set
- Tokens are valid (not expired during initial setup)

### Tokens Not Updating

**Check**:
- Secrets Manager permissions in Lambda role
- CloudWatch logs for error messages
- Secret name matches configuration

### Account IDs Wrong

**Verify** using Questrade API:
```bash
# Get your access token first
curl "https://login.questrade.com/oauth2/token?grant_type=refresh_token&refresh_token=YOUR_TOKEN"

# Then list accounts
curl "API_SERVER/v1/accounts" -H "Authorization: Bearer ACCESS_TOKEN"
```

## Best Practices

✅ **Label accounts clearly** (`primary`, `spouse`, `child`) for easy identification
✅ **Keep tokens separate** - one per Questrade login
✅ **Monitor logs** after first run to verify both accounts sync
✅ **Test tokens** before adding to production
✅ **Document** which account IDs belong to whom

## Security

- Each person's Questrade credentials remain separate
- Tokens stored securely in AWS Secrets Manager
- GitHub secrets are encrypted
- No credentials committed to repository
- Tokens auto-rotate independently

## Cost

Same as single account: ~$0.50/month for Secrets Manager, regardless of number of tokens stored.
