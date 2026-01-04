# Questrade to Lunch Money Sync

Automated synchronization of investment transactions from Questrade to Lunch Money using AWS Lambda.

## Overview

This project provides a serverless solution to automatically import your Questrade investment account activities into Lunch Money for comprehensive financial tracking. Since Questrade isn't available through Plaid, this integration uses both APIs directly.

## Features

- Automatic synchronization of Questrade account activities (trades, dividends, cash transactions)
- Scheduled execution via AWS Lambda
- Configurable sync intervals
- Duplicate transaction detection
- Error handling and logging

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│  Questrade  │ ───> │  AWS Lambda  │ ───> │ Lunch Money  │
│     API     │      │   Function   │      │     API      │
└─────────────┘      └──────────────┘      └──────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │  CloudWatch  │
                    │     Logs     │
                    └──────────────┘
```

## Prerequisites

- Questrade account with API access enabled
- Lunch Money account with API access
- AWS account
- Node.js 18.x or later (for local development)

## API Documentation

### Lunch Money API
- **Documentation**: [https://lunchmoney.dev/](https://lunchmoney.dev/)
- **Authentication**: Bearer token (get from [developers page](https://my.lunchmoney.app/developers))
- **Key Endpoint**: `POST /v1/transactions` - Create transactions

### Questrade API
- **Documentation**: [https://www.questrade.com/api/documentation/getting-started](https://www.questrade.com/api/documentation/getting-started)
- **Authentication**: OAuth 2.0 with refresh tokens
- **Key Endpoint**: `GET /v1/accounts/{accountId}/activities` - Retrieve account activities
- **Data Limit**: Maximum 31 days per request

## Setup

### 1. Get API Credentials

#### Questrade
1. Log into your Questrade account
2. Navigate to the API section in the security center
3. Register your application to get a Client ID
4. Generate a refresh token

#### Lunch Money
1. Log into Lunch Money
2. Go to Settings → Developers
3. Generate an API access token

### 2. Configure Environment Variables

Create a `.env` file (for local development) or configure in AWS Lambda:

```bash
QUESTRADE_REFRESH_TOKEN=your_questrade_refresh_token
LUNCHMONEY_API_TOKEN=your_lunchmoney_api_token
QUESTRADE_ACCOUNT_IDS=account_id_1,account_id_2
SYNC_DAYS_BACK=31
```

### 3. Deploy to AWS Lambda

```bash
# Install dependencies
npm install

# Package for Lambda
npm run package

# Deploy using AWS CLI or AWS Console
aws lambda create-function \
  --function-name questrade-lunchmoney-sync \
  --runtime nodejs18.x \
  --handler index.handler \
  --zip-file fileb://function.zip \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-execution-role
```

### 4. Set Up CloudWatch Events

Configure a CloudWatch Events rule to trigger the Lambda function on your desired schedule:

```bash
# Daily sync at 8 AM UTC
aws events put-rule \
  --name questrade-sync-daily \
  --schedule-expression "cron(0 8 * * ? *)"

aws events put-targets \
  --rule questrade-sync-daily \
  --targets "Id"="1","Arn"="arn:aws:lambda:REGION:ACCOUNT_ID:function:questrade-lunchmoney-sync"
```

## Development

### Local Testing

```bash
# Install dependencies
npm install

# Run locally
npm run dev

# Run tests
npm test
```

### Project Structure

```
questrade-lunchmoney-sync/
├── src/
│   ├── index.js              # Lambda handler
│   ├── questrade.js          # Questrade API client
│   ├── lunchmoney.js         # Lunch Money API client
│   ├── sync.js               # Sync logic
│   └── utils.js              # Helper functions
├── tests/
│   └── sync.test.js
├── package.json
├── .env.example
├── .gitignore
└── README.md
```

## Transaction Mapping

Questrade activities are mapped to Lunch Money transactions as follows:

| Questrade Field | Lunch Money Field |
|----------------|-------------------|
| `transactionDate` | `date` |
| `netAmount` | `amount` |
| `description` | `payee` |
| `type` | `notes` (for reference) |
| `symbol` | `notes` (for trades) |

## Error Handling

- OAuth token refresh failures are logged and will retry on next execution
- Duplicate transactions are detected using transaction date + amount + description
- API rate limits are respected with exponential backoff
- All errors are logged to CloudWatch

## Cost Estimate

Based on typical usage:
- AWS Lambda: ~$0.20/month (1 daily execution, 128MB memory, 10s duration)
- CloudWatch Logs: ~$0.50/month
- **Total**: ~$0.70/month

## Security Considerations

- Store API tokens in AWS Secrets Manager for production use
- Use IAM roles with least privilege
- Enable CloudWatch Logs encryption
- Regularly rotate Questrade refresh tokens

## Limitations

- Questrade API provides data for the past 16 months only
- Maximum 31 days of data per API request
- Historical data sync requires multiple API calls

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## License

MIT

## Resources

- [Lunch Money API Documentation](https://lunchmoney.dev/)
- [Questrade API Documentation](https://www.questrade.com/api/documentation/getting-started)
- [Questrade Account Activities Endpoint](https://www.questrade.com/api/documentation/rest-operations/account-calls/accounts-id-activities)
- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
