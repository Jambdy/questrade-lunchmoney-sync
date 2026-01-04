# Multiple Questrade Accounts Setup

This guide explains how to sync multiple Questrade accounts to Lunch Money using a simple, flexible configuration.

## Why Multiple Accounts?

Each Questrade login requires its own OAuth refresh token. You might have:
- Multiple personal accounts (TFSA, RRSP, etc.)
- Accounts for different family members
- Any combination of investment accounts

## Simplified Configuration

The setup is extremely simple: one GitHub secret with a comma-separated list of account IDs and tokens.

### GitHub Secret (Initial Setup Only)

Set up this secret in your GitHub repository (Settings → Secrets and variables → Actions):

**Secret Name:** `QUESTRADE_TOKENS`

**Format:** `accountId:token,accountId:token,accountId:token,...`

**Example:**
```
QUESTRADE_TOKENS=12345678:xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0,12345679:xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0,87654321:yBDuQHD-CPFwn8LiiH1pJwj-SPIeLBht1
```

In this example:
- Account `12345678` and `12345679` share the same token (both under the same Questrade login)
- Account `87654321` uses a different token (different Questrade login)

### Secrets Manager (Runtime)

After the first deployment, tokens are stored in AWS Secrets Manager:

**Secret Name:** `questrade-lunchmoney/questrade-tokens`

**Format (JSON):**
```json
{
  "12345678": "refresh_token_for_account_12345678",
  "12345679": "refresh_token_for_account_12345679",
  "87654321": "refresh_token_for_account_87654321"
}
```

- **Key:** Questrade account ID
- **Value:** Refresh token for that account
- Lambda extracts account IDs from the JSON keys automatically
- Tokens are automatically updated after each sync

## How It Works

1. **Initial Setup:**
   - You provide `QUESTRADE_TOKENS` as a GitHub secret
   - GitHub Actions parses it and creates Secrets Manager secret

2. **Each Lambda Run:**
   - Reads all tokens from Secrets Manager
   - Extracts account IDs from the JSON keys
   - Syncs each account with its corresponding token
   - Updates tokens in Secrets Manager if they changed

3. **Result:**
   - All accounts stay authenticated
   - Tokens automatically rotate (never expire)
   - All transactions appear in Lunch Money

## Getting Your Configuration

### Step 1: Get Account IDs

#### Option A: Via Questrade Website
1. Log into Questrade
2. View your accounts
3. Account number is displayed (usually 8 digits)
4. Note down all account IDs you want to sync

#### Option B: Via API (Advanced)
```bash
# Use your refresh token to get account IDs
curl "https://login.questrade.com/oauth2/token?grant_type=refresh_token&refresh_token=YOUR_TOKEN"

# Use the api_server and access_token from response
curl "API_SERVER/v1/accounts" -H "Authorization: Bearer ACCESS_TOKEN"
```

### Step 2: Get Refresh Tokens

For each unique Questrade login (not each account):

1. Log into that Questrade account
2. Go to Account Management → API Access
3. Create app: "Lunch Money Sync"
4. Generate refresh token
5. Copy token immediately (shown only once)

**Important:** If multiple accounts are under the same Questrade login, they share the same token!

### Step 3: Build QUESTRADE_TOKENS

Format: `accountId1:token1,accountId2:token2,...`

**Example 1: Single Login, Multiple Accounts**
```
QUESTRADE_TOKENS=12345678:xazTpGC...,12345679:xazTpGC...
```
(Same token for both accounts under one login)

**Example 2: Multiple Logins**
```
QUESTRADE_TOKENS=12345678:xazTpGC...,87654321:yBDuQHD...
```
(Different tokens for different logins)

**Example 3: Mix of Both**
```
QUESTRADE_TOKENS=11111111:tokenA,22222222:tokenA,33333333:tokenB,44444444:tokenC
```
(Accounts 11111111 and 22222222 share tokenA, others have unique tokens)

## GitHub Actions Setup

### Required Secrets

Go to your repository → Settings → Secrets and variables → Actions

| Secret Name | Description | Example |
|------------|-------------|---------|
| `QUESTRADE_TOKENS` | Comma-separated `accountId:token` pairs | `12345:token1,67890:token2` |
| `LUNCHMONEY_API_TOKEN` | Lunch Money API access token | `lm_abc123...` |
| `AWS_ACCESS_KEY_ID` | AWS IAM access key ID | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret access key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |

**Note:** After initial deployment, tokens are automatically managed in AWS Secrets Manager. The `QUESTRADE_TOKENS` GitHub secret is only used if you need to redeploy or add new accounts.

## Example Setups

### Example 1: Personal Accounts Only

You have:
- TFSA account: 12345678
- RRSP account: 12345679
- Both under one Questrade login with token: `xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0`

**Configuration:**
```
QUESTRADE_TOKENS=12345678:xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0,12345679:xazTpGC-BOEvm7KhhG0oIvi-ROHdKAgs0
```

### Example 2: Multiple Family Members

You have:
- Your TFSA: 11111111 (your login token: `tokenA`)
- Your RRSP: 22222222 (your login token: `tokenA`)
- Partner's TFSA: 33333333 (partner's login token: `tokenB`)
- Partner's RRSP: 44444444 (partner's login token: `tokenB`)

**Configuration:**
```
QUESTRADE_TOKENS=11111111:tokenA,22222222:tokenA,33333333:tokenB,44444444:tokenB
```

### Example 3: Many Accounts

No limit on number of accounts! Just keep adding to the comma-separated list:

```
QUESTRADE_TOKENS=11111:t1,22222:t1,33333:t2,44444:t3,55555:t3,66666:t4
```

## Adding More Accounts

To add a new account:

1. **Get the account ID** from Questrade
2. **Get the refresh token** (if it's a new login) or reuse an existing token
3. **Update GitHub secret** `QUESTRADE_TOKENS`: append `,newAccountId:token`
4. **Redeploy:**
   ```bash
   git commit --allow-empty -m "Add new account"
   git push origin main
   ```

Or trigger manual deployment from GitHub Actions UI.

That's it! The new account will be synced on the next Lambda run.

## Removing Accounts

To remove an account:

1. **Update GitHub secret** `QUESTRADE_TOKENS`: remove the `accountId:token` entry
2. **Update Secrets Manager manually** (or redeploy):
   ```bash
   # Get current secret
   aws secretsmanager get-secret-value \
     --secret-id questrade-lunchmoney/questrade-tokens \
     --query 'SecretString' --output text | jq

   # Update to remove the account ID
   aws secretsmanager put-secret-value \
     --secret-id questrade-lunchmoney/questrade-tokens \
     --secret-string '{"keep_this_account":"token",...}'
   ```

## Monitoring

### CloudWatch Logs

Look for log entries like:
```
Starting sync for 3 Questrade account(s): 12345678, 12345679, 87654321
Processing account 12345678
  Account 12345678: 5 new, 2 skipped
Processing account 12345679
  Account 12345679: 3 new, 1 skipped
Processing account 87654321
  Account 87654321: 2 new, 0 skipped
3 Questrade token(s) updated
✅ Successfully updated Questrade refresh tokens in Secrets Manager
  - Updated token for account: 12345678
  - Updated token for account: 12345679
  - Updated token for account: 87654321
```

### Lambda Response

```json
{
  "statusCode": 200,
  "body": {
    "message": "Sync completed successfully",
    "results": {
      "12345678": {"new_transactions": 5, "skipped_duplicates": 2},
      "12345679": {"new_transactions": 3, "skipped_duplicates": 1},
      "87654321": {"new_transactions": 2, "skipped_duplicates": 0}
    },
    "totals": {
      "new_transactions": 10,
      "skipped_duplicates": 3
    },
    "accounts_processed": 3,
    "tokens_rotated": 3,
    "tokens_auto_updated": true
  }
}
```

## Troubleshooting

### Only Some Accounts Syncing

**Check:**
- All account IDs are in the Secrets Manager JSON
- Each account ID has a valid token
- Tokens haven't expired during setup

**View Secrets Manager:**
```bash
aws secretsmanager get-secret-value \
  --secret-id questrade-lunchmoney/questrade-tokens \
  --query 'SecretString' --output text | jq
```

### Tokens Not Updating

**Check:**
- Secrets Manager permissions in Lambda role
- CloudWatch logs for error messages
- Secret name matches configuration

### Wrong Account IDs

**Verify** using Questrade API:
```bash
# Get your access token first
curl "https://login.questrade.com/oauth2/token?grant_type=refresh_token&refresh_token=YOUR_TOKEN"

# Then list accounts
curl "API_SERVER/v1/accounts" -H "Authorization: Bearer ACCESS_TOKEN"
```

### Deployment Fails

If SAM deployment fails with "Parameter QuestradeAccounts does not exist":
- You may be using an old deployment. Delete the stack and redeploy:
```bash
aws cloudformation delete-stack --stack-name questrade-lunchmoney-sync
# Wait for deletion, then push to GitHub to redeploy
```

## Best Practices

✅ **Label clearly** - Use comments in your documentation to track which accounts belong to whom
✅ **Keep tokens secure** - Never commit tokens to repository
✅ **Monitor logs** after first run to verify all accounts sync
✅ **Test tokens** before adding to production
✅ **Document** which account IDs map to which accounts/people

## Security

- Each person's Questrade credentials remain separate
- Tokens stored securely in AWS Secrets Manager
- GitHub secrets are encrypted
- No credentials committed to repository
- Tokens auto-rotate independently

## Cost

Same as single account: ~$0.50/month for Secrets Manager, regardless of number of accounts/tokens stored.
