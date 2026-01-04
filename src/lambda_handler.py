import os
import logging
import json
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from .questrade import QuestradeClient
from .lunchmoney import LunchMoneyClient
from .sync import TransactionSync

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')


def get_secret(secret_name: str) -> Optional[str]:
    """
    Retrieve a secret from AWS Secrets Manager.

    Args:
        secret_name: Name of the secret to retrieve

    Returns:
        Secret value as string, or None if not found
    """
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)

        # Secrets can be stored as string or binary
        if 'SecretString' in response:
            return response['SecretString']
        else:
            # Binary secrets (base64 encoded)
            import base64
            return base64.b64decode(response['SecretBinary']).decode('utf-8')

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            logger.warning(f"Secret {secret_name} not found in Secrets Manager")
        elif error_code == 'AccessDeniedException':
            logger.error(f"Access denied to secret {secret_name}")
        else:
            logger.error(f"Error retrieving secret {secret_name}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving secret {secret_name}: {str(e)}")
        return None


def update_secret(secret_name: str, secret_value: str) -> bool:
    """
    Update a secret in AWS Secrets Manager.

    Args:
        secret_name: Name of the secret to update
        secret_value: New value for the secret

    Returns:
        True if successful, False otherwise
    """
    try:
        secrets_client.put_secret_value(
            SecretId=secret_name,
            SecretString=secret_value
        )
        logger.info(f"Successfully updated secret {secret_name}")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            logger.error(f"Secret {secret_name} not found. Cannot update.")
        elif error_code == 'AccessDeniedException':
            logger.error(f"Access denied to update secret {secret_name}")
        else:
            logger.error(f"Error updating secret {secret_name}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error updating secret {secret_name}: {str(e)}")
        return False


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function for syncing Questrade to Lunch Money.

    Environment Variables Required:
        QUESTRADE_SECRET_NAME: Name of Secrets Manager secret for Questrade tokens (optional)
        USE_SECRETS_MANAGER: Whether to use Secrets Manager (default: 'true')
        QUESTRADE_REFRESH_TOKEN: Questrade OAuth refresh token (fallback, can be JSON for multiple)
        LUNCHMONEY_API_TOKEN: Lunch Money API access token
        QUESTRADE_ACCOUNTS: JSON mapping of account labels to account IDs
        SYNC_DAYS_BACK: Number of days to sync (default: 31, max: 31)
        LUNCHMONEY_ASSET_ID: Optional Lunch Money asset ID to associate transactions

    QUESTRADE_ACCOUNTS format (JSON):
        {
          "primary": {"account_ids": ["123456"], "token_key": "primary"},
          "spouse": {"account_ids": ["789012"], "token_key": "spouse"}
        }

    Secrets Manager format (JSON):
        {
          "primary": "refresh_token_for_primary_account",
          "spouse": "refresh_token_for_spouse_account"
        }

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Response dictionary with status and results
    """
    try:
        # Get configuration from environment variables
        use_secrets_manager = os.environ.get('USE_SECRETS_MANAGER', 'true').lower() == 'true'
        secret_name = os.environ.get('QUESTRADE_SECRET_NAME', 'questrade-lunchmoney/questrade-tokens')
        lunchmoney_api_token = os.environ.get('LUNCHMONEY_API_TOKEN')
        accounts_config_str = os.environ.get('QUESTRADE_ACCOUNTS', '')
        days_back = int(os.environ.get('SYNC_DAYS_BACK', '31'))
        asset_id_str = os.environ.get('LUNCHMONEY_ASSET_ID')

        # Parse accounts configuration
        try:
            accounts_config = json.loads(accounts_config_str) if accounts_config_str else {}
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid QUESTRADE_ACCOUNTS JSON: {str(e)}")

        # Get Questrade refresh tokens from Secrets Manager or environment variable
        questrade_tokens = {}
        if use_secrets_manager:
            logger.info(f"Retrieving Questrade refresh tokens from Secrets Manager: {secret_name}")
            tokens_json = get_secret(secret_name)
            if tokens_json:
                try:
                    questrade_tokens = json.loads(tokens_json)
                    logger.info(f"Loaded {len(questrade_tokens)} Questrade tokens from Secrets Manager")
                except json.JSONDecodeError:
                    # Single token (backward compatibility)
                    questrade_tokens = {"default": tokens_json}
                    logger.info("Loaded single Questrade token from Secrets Manager")

        # Fallback to environment variable if Secrets Manager not used or failed
        if not questrade_tokens:
            logger.info("Falling back to environment variable for Questrade refresh token")
            token_env = os.environ.get('QUESTRADE_REFRESH_TOKEN', '')
            if token_env:
                try:
                    questrade_tokens = json.loads(token_env)
                except json.JSONDecodeError:
                    # Single token
                    questrade_tokens = {"default": token_env}

        # Validate required configuration
        if not questrade_tokens:
            raise ValueError("QUESTRADE_REFRESH_TOKEN not found in Secrets Manager or environment variables")
        if not lunchmoney_api_token:
            raise ValueError("LUNCHMONEY_API_TOKEN environment variable is required")
        if not accounts_config:
            raise ValueError("QUESTRADE_ACCOUNTS environment variable is required")

        # Parse asset ID if provided
        asset_id = int(asset_id_str) if asset_id_str else None

        logger.info(f"Starting sync for {len(accounts_config)} Questrade account group(s)")
        logger.info(f"Syncing last {days_back} days")

        # Initialize Lunch Money client (shared across all accounts)
        lunchmoney_client = LunchMoneyClient(lunchmoney_api_token)

        # Track all results and updated tokens
        all_results = {}
        updated_tokens = {}
        total_new = 0
        total_skipped = 0

        # Process each account group
        for account_label, account_info in accounts_config.items():
            account_ids = account_info.get('account_ids', [])
            token_key = account_info.get('token_key', account_label)

            if not account_ids:
                logger.warning(f"No account IDs specified for {account_label}, skipping")
                continue

            # Get the token for this account group
            refresh_token = questrade_tokens.get(token_key)
            if not refresh_token:
                logger.error(f"No refresh token found for {account_label} (key: {token_key}), skipping")
                continue

            logger.info(f"Processing {account_label}: {len(account_ids)} account(s)")

            # Initialize Questrade client for this account group
            questrade_client = QuestradeClient(refresh_token)

            # Initialize sync handler
            sync_handler = TransactionSync(
                questrade_client=questrade_client,
                lunchmoney_client=lunchmoney_client,
                asset_id=asset_id
            )

            # Perform sync for this account group
            group_results = sync_handler.sync_multiple_accounts(
                account_ids=account_ids,
                days_back=days_back
            )

            # Store results with account label prefix
            for account_id, (new_count, skipped_count) in group_results.items():
                all_results[f"{account_label}:{account_id}"] = (new_count, skipped_count)
                total_new += new_count
                total_skipped += skipped_count

            # Check if token was updated
            new_token = questrade_client.get_current_refresh_token()
            if new_token != refresh_token:
                updated_tokens[token_key] = new_token
                logger.info(f"Token updated for {account_label}")

        # Log results
        logger.info(f"Sync completed: {total_new} new transactions, {total_skipped} duplicates skipped")
        for account_id, (new_count, skipped_count) in all_results.items():
            logger.info(f"  Account {account_id}: {new_count} new, {skipped_count} skipped")

        # Update refresh tokens if any changed
        tokens_updated = False
        if updated_tokens:
            logger.info(f"{len(updated_tokens)} Questrade token(s) updated")

            # Automatically update Secrets Manager if enabled
            if use_secrets_manager:
                # Merge updated tokens with existing tokens
                merged_tokens = {**questrade_tokens, **updated_tokens}
                tokens_json = json.dumps(merged_tokens)

                logger.info(f"Updating Secrets Manager secret: {secret_name}")
                tokens_updated = update_secret(secret_name, tokens_json)

                if tokens_updated:
                    logger.info("✅ Successfully updated Questrade refresh tokens in Secrets Manager")
                    for token_key in updated_tokens.keys():
                        logger.info(f"  - Updated token for: {token_key}")
                else:
                    logger.error("❌ Failed to update Questrade refresh tokens in Secrets Manager")
                    logger.warning("Manual update required for tokens:")
                    for token_key, token_value in updated_tokens.items():
                        logger.warning(f"  - {token_key}: {token_value[:10]}...")
            else:
                logger.warning("Secrets Manager not enabled.")
                logger.warning("Please manually update your QUESTRADE_REFRESH_TOKEN with:")
                logger.warning(json.dumps(updated_tokens, indent=2))

        return {
            'statusCode': 200,
            'body': {
                'message': 'Sync completed successfully',
                'results': {
                    account_id: {
                        'new_transactions': new_count,
                        'skipped_duplicates': skipped_count
                    }
                    for account_id, (new_count, skipped_count) in all_results.items()
                },
                'totals': {
                    'new_transactions': total_new,
                    'skipped_duplicates': total_skipped
                },
                'accounts_processed': len(accounts_config),
                'tokens_rotated': len(updated_tokens),
                'tokens_auto_updated': tokens_updated,
                'using_secrets_manager': use_secrets_manager
            }
        }

    except Exception as e:
        logger.error(f"Error during sync: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {
                'message': 'Sync failed',
                'error': str(e)
            }
        }


def main():
    """
    Main function for local testing.
    Requires .env file with environment variables.
    """
    from dotenv import load_dotenv

    # Load environment variables from .env file
    load_dotenv()

    # Call the handler
    result = handler({}, None)

    # Print result
    print("\n" + "="*50)
    print("SYNC RESULTS")
    print("="*50)
    print(f"Status Code: {result['statusCode']}")
    print(f"\nBody:")

    if result['statusCode'] == 200:
        body = result['body']
        print(f"  Message: {body['message']}")
        print(f"\n  Totals:")
        print(f"    New Transactions: {body['totals']['new_transactions']}")
        print(f"    Skipped Duplicates: {body['totals']['skipped_duplicates']}")
        print(f"\n  Per-Account Results:")
        for account_id, account_results in body['results'].items():
            print(f"    Account {account_id}:")
            print(f"      New: {account_results['new_transactions']}")
            print(f"      Skipped: {account_results['skipped_duplicates']}")

        if body.get('new_refresh_token'):
            print(f"\n  ⚠️  IMPORTANT: Update your .env with new refresh token:")
            print(f"  {body['new_refresh_token']}")
    else:
        print(f"  Error: {result['body']['error']}")

    print("="*50 + "\n")


if __name__ == '__main__':
    main()
