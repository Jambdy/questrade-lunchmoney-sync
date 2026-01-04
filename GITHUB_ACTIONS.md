# GitHub Actions Deployment Guide

This guide explains how to deploy the Questrade to Lunch Money sync application using GitHub Actions with repository secrets.

## Overview

The GitHub Actions workflows automate:
- **Testing** on every push and pull request
- **Deployment** to AWS on pushes to main/master branch
- **Manual deployments** via GitHub UI

## Workflows

### 1. [.github/workflows/test.yml](.github/workflows/test.yml) - Tests
Runs on every push and PR:
- Tests on Python 3.9, 3.10, 3.11, and 3.12
- Code coverage reporting
- SAM template validation
- Linting (optional)

### 2. [.github/workflows/deploy.yml](.github/workflows/deploy.yml) - Deployment
Runs on push to main/master or manual trigger:
- Runs tests first
- Builds SAM application
- Deploys to AWS using parameters from secrets/variables
- Runs optional smoke test
- Posts deployment summary

## Setup Instructions

### Step 1: Configure AWS Credentials

You have two options for AWS authentication:

#### Option A: IAM Access Keys (Simpler)

1. Create an IAM user with deployment permissions
2. Generate access keys
3. Add to GitHub secrets (see Step 2)

Required IAM permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "iam:*",
        "s3:*",
        "logs:*",
        "events:*",
        "sns:*",
        "cloudwatch:*",
        "secretsmanager:*"
      ],
      "Resource": "*"
    }
  ]
}
```

#### Option B: OIDC (More Secure - Recommended)

1. Set up OIDC provider in AWS:
   ```bash
   # Use AWS Console or CLI to create OIDC provider
   # Provider URL: https://token.actions.githubusercontent.com
   # Audience: sts.amazonaws.com
   ```

2. Create IAM role with trust policy:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub": "repo:YOUR_USERNAME/questrade-lunchmoney-sync:*"
           }
         }
       }
     ]
   }
   ```

3. Update [.github/workflows/deploy.yml](.github/workflows/deploy.yml):
   - Uncomment the OIDC lines
   - Comment out the access key lines
   - Add `AWS_ROLE_ARN` to secrets

### Step 2: Configure GitHub Secrets

Go to your repository → Settings → Secrets and variables → Actions

#### Required Secrets

Add these as **Repository Secrets**:

| Secret Name | Description | Example |
|------------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | AWS IAM access key ID (if using Option A) | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret access key (if using Option A) | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `AWS_ROLE_ARN` | AWS IAM role ARN (if using OIDC Option B) | `arn:aws:iam::123456789012:role/GitHubActionsRole` |
| `QUESTRADE_TOKENS` | Comma-separated `accountId:token` pairs (initial only) ⚡ | `12345:token1,67890:token2` |
| `LUNCHMONEY_API_TOKEN` | Lunch Money API access token | `lm_abc123...` |

⚡ **Questrade Token Auto-Rotation**: The `QUESTRADE_TOKENS` secret is only needed for the **initial deployment**. After that, tokens are automatically stored and rotated in AWS Secrets Manager. You'll never need to manually update them again! See [SECRETS_MANAGER.md](SECRETS_MANAGER.md) and [MULTI_ACCOUNT_SETUP.md](MULTI_ACCOUNT_SETUP.md) for details.

**To add a secret:**
1. Click "New repository secret"
2. Enter the name exactly as shown above
3. Paste the value
4. Click "Add secret"

#### Optional Variables

Add these as **Repository Variables** (not secrets - they're not sensitive):

| Variable Name | Description | Default |
|--------------|-------------|---------|
| `SYNC_DAYS_BACK` | Number of days to sync | `31` |
| `LUNCHMONEY_ASSET_ID` | Lunch Money asset ID | `` (empty) |
| `SYNC_SCHEDULE` | Cron expression for sync | `cron(0 8 * * ? *)` |
| `LOG_RETENTION_DAYS` | CloudWatch log retention days | `30` |

**To add a variable:**
1. Go to Settings → Secrets and variables → Actions → Variables tab
2. Click "New repository variable"
3. Enter name and value
4. Click "Add variable"

### Step 3: Configure Environment (Optional but Recommended)

For better control and protection:

1. Go to Settings → Environments
2. Click "New environment"
3. Name it `production`
4. Configure protection rules:
   - ✅ Required reviewers (add yourself)
   - ✅ Wait timer (optional: 5 minutes)
   - Deployment branches: Selected branches → Add `main` or `master`

This adds manual approval before deployments!

### Step 4: Enable Workflows

1. Go to the **Actions** tab in your repository
2. You should see two workflows:
   - "Tests"
   - "Deploy to AWS"
3. If prompted, click "I understand my workflows, go ahead and enable them"

### Step 5: Initial Deployment

You have two options:

#### Option A: Push to main/master (Automatic)

```bash
git add .
git commit -m "Add GitHub Actions workflows"
git push origin main
```

The deployment will run automatically!

#### Option B: Manual Trigger (via GitHub UI)

1. Go to Actions tab
2. Click "Deploy to AWS" workflow
3. Click "Run workflow"
4. Select branch and environment
5. Click "Run workflow"

This is useful for:
- First deployment
- Testing changes
- Redeployment after token updates

## Monitoring Deployments

### View Workflow Runs

1. Go to **Actions** tab
2. Click on a workflow run
3. Click on the job to see detailed logs

### Deployment Summary

After deployment, check the Summary section for:
- Stack name and region
- Function ARN
- SNS topic ARN
- Configuration details

### Check AWS Resources

```bash
# View CloudFormation stack
aws cloudformation describe-stacks --stack-name questrade-lunchmoney-sync

# View Lambda logs
aws logs tail /aws/lambda/questrade-lunchmoney-sync --follow

# Test Lambda manually
aws lambda invoke \
  --function-name questrade-lunchmoney-sync \
  --cli-binary-format raw-in-base64-out \
  --payload '{}' \
  response.json && cat response.json
```

## Updating Configuration

### Update Secrets/Variables

1. Go to Settings → Secrets and variables → Actions
2. Click on the secret/variable you want to update
3. Click "Update secret" or "Update variable"
4. Enter new value
5. Save

### Trigger Redeployment

After updating secrets/variables, redeploy:

**Option 1: Push a commit**
```bash
git commit --allow-empty -m "Redeploy with updated secrets"
git push origin main
```

**Option 2: Manual trigger**
- Go to Actions → Deploy to AWS → Run workflow

### Update Questrade Refresh Token

The Questrade refresh token updates after each use. To update it:

1. Check Lambda logs for the new token:
   ```bash
   aws logs tail /aws/lambda/questrade-lunchmoney-sync --since 1h | grep "refresh_token"
   ```

2. Update the GitHub secret:
   - Settings → Secrets → `QUESTRADE_REFRESH_TOKEN` → Update

3. Redeploy (optional - next run will use new token from environment)

## Workflow Features

### Automatic Testing

Every push and PR runs:
- Unit tests on multiple Python versions
- Code coverage analysis
- SAM template validation
- Linting checks

### Deployment Protection

The workflow includes:
- ✅ Tests must pass before deployment
- ✅ Optional environment approval
- ✅ Smoke test after deployment (on staging)
- ✅ Automatic rollback on failure

### Manual Deployment Control

Use workflow_dispatch to:
- Deploy to specific environment
- Test before merging
- Redeploy with updated configuration

### Deployment Summary

After each deployment, the workflow posts a summary with:
- Stack details
- Resource ARNs
- Configuration values
- Deployment status

## Troubleshooting

### Deployment Fails: "AccessDenied"

**Problem**: AWS credentials lack permissions

**Solution**:
- Verify IAM user/role has required permissions (see Step 1)
- Check AWS credentials in GitHub secrets are correct

### Deployment Fails: "Invalid Refresh Token"

**Problem**: Questrade refresh token expired or invalid

**Solution**:
1. Get a new refresh token from Questrade
2. Update GitHub secret `QUESTRADE_REFRESH_TOKEN`
3. Retry deployment

### Tests Fail

**Problem**: Tests failing in CI but pass locally

**Solution**:
- Check Python version compatibility
- Ensure all dependencies in requirements.txt
- Review test logs in Actions tab

### Workflow Doesn't Trigger

**Problem**: Pushing to main but workflow doesn't run

**Solution**:
- Ensure workflows are enabled (Actions tab)
- Check branch name matches workflow trigger (main vs master)
- Verify .github/workflows/ directory is in repository root

### Can't See Secrets

**Problem**: Need to verify secret values

**Solution**:
- Secrets are hidden by design (security feature)
- To verify, use a temporary workflow step:
  ```yaml
  - name: Debug (remove after)
    run: echo "Token length: ${#QUESTRADE_REFRESH_TOKEN}"
    env:
      QUESTRADE_REFRESH_TOKEN: ${{ secrets.QUESTRADE_REFRESH_TOKEN }}
  ```
- Check length matches expected value
- **Remove debug step after verification!**

## Security Best Practices

### Do's ✅

- Use repository secrets for sensitive data
- Use environment protection rules
- Enable branch protection on main/master
- Use OIDC instead of long-lived access keys
- Regularly rotate tokens
- Review workflow logs for exposed secrets
- Use least-privilege IAM policies

### Don'ts ❌

- Don't commit secrets to repository
- Don't echo secrets in workflow logs
- Don't use personal AWS credentials
- Don't disable security features
- Don't share repository access unnecessarily

## Advanced Configuration

### Deploy to Multiple Environments

Create additional environments:

1. **Staging Environment**:
   - Settings → Environments → New environment → `staging`
   - Add staging-specific secrets/variables
   - Deploy with different stack name

2. **Update workflow** to use environment-specific values:
   ```yaml
   env:
     STACK_NAME: questrade-lunchmoney-sync-${{ github.event.inputs.environment }}
   ```

### Slack/Discord Notifications

Add notification step to [.github/workflows/deploy.yml](.github/workflows/deploy.yml):

```yaml
- name: Notify Slack
  if: always()
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
    webhook_url: ${{ secrets.SLACK_WEBHOOK_URL }}
```

### Scheduled Deployments

Add to workflow triggers:
```yaml
on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
```

### Deploy on Release

```yaml
on:
  release:
    types: [published]
```

## Cost Optimization

### GitHub Actions

- Public repositories: **Free unlimited minutes**
- Private repositories: **2,000 free minutes/month**
- Each deployment uses ~5-10 minutes

### AWS Resources

Same as manual deployment (~$0.90/month)

## Comparison: GitHub Actions vs Manual Deployment

| Feature | GitHub Actions | Manual SAM CLI |
|---------|---------------|----------------|
| Automation | ✅ Automatic | ❌ Manual |
| CI/CD | ✅ Built-in | ❌ Separate setup |
| Testing | ✅ Automatic | ❌ Manual |
| Approval | ✅ Environment rules | ❌ None |
| Audit Trail | ✅ Full history | ⚠️ Limited |
| Multi-environment | ✅ Easy | ⚠️ Manual |
| Secret Management | ✅ GitHub Secrets | ⚠️ Local .env |
| Team Collaboration | ✅ Excellent | ⚠️ Limited |
| Setup Complexity | ⚠️ Medium | ✅ Simple |
| Local Testing | ⚠️ Requires checkout | ✅ Easy |

## Migration from Manual to GitHub Actions

If you deployed manually and want to migrate:

1. **Don't delete existing stack** - GitHub Actions will update it
2. Add secrets/variables to GitHub
3. Push workflows to repository
4. First deployment will update existing stack
5. Verify everything works
6. Delete local .env file (keep .env.example)

## Next Steps

After successful deployment:

1. ✅ Subscribe to SNS error notifications
2. ✅ Set up CloudWatch dashboard
3. ✅ Configure branch protection rules
4. ✅ Add team members as collaborators
5. ✅ Document any custom configuration
6. ✅ Test the deployment workflow

## Support

- Check workflow logs in Actions tab
- Review AWS CloudWatch logs
- See main [DEPLOYMENT.md](DEPLOYMENT.md) for AWS-specific help
- Open GitHub issue for problems

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Encrypted Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [AWS SAM with GitHub Actions](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-generating-example-ci-cd-others.html)
- [OIDC with GitHub Actions](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
