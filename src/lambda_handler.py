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
        QUESTRADE_SECRET_NAME: Name of Secrets Manager secret for Questrade tokens
        USE_SECRETS_MANAGER: Whether to use Secrets Manager (default: 'true')
        LUNCHMONEY_API_TOKEN: Lunch Money API access token
        SYNC_DAYS_BACK: Number of days to sync (default: 31, max: 31)
        LUNCHMONEY_ASSET_ID: Optional Lunch Money asset ID to associate transactions

    Secrets Manager format (JSON):
        {
          "12345": "refresh_token_for_account_12345",
          "67890": "refresh_token_for_account_67890",
          "11111": "refresh_token_for_account_11111"
        }

    Account IDs are extracted directly from the Secrets Manager JSON keys.
    Each key represents a Questrade account ID, and its value is the refresh token.

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
        days_back = int(os.environ.get('SYNC_DAYS_BACK', '31'))
        asset_id_str = os.environ.get('LUNCHMONEY_ASSET_ID')

        # Get Questrade refresh tokens from Secrets Manager
        # The JSON format is: {"account_id": "token", "account_id2": "token2", ...}
        # Account IDs are extracted from the JSON keys
        all_tokens = {}
        if use_secrets_manager:
            logger.info(f"Retrieving Questrade tokens from Secrets Manager: {secret_name}")
            tokens_json = get_secret(secret_name)
            if tokens_json:
                try:
                    all_tokens = json.loads(tokens_json)
                    logger.info(f"Loaded tokens for {len(all_tokens)} Questrade account(s) from Secrets Manager")
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in Secrets Manager secret {secret_name}: {str(e)}")
            else:
                raise ValueError(f"Could not retrieve secret {secret_name} from Secrets Manager")
        else:
            # Fallback to environment variable if Secrets Manager not enabled
            logger.info("Secrets Manager disabled, falling back to QUESTRADE_REFRESH_TOKEN environment variable")
            token_env = os.environ.get('QUESTRADE_REFRESH_TOKEN', '')
            if token_env:
                try:
                    all_tokens = json.loads(token_env)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in QUESTRADE_REFRESH_TOKEN: {str(e)}")
            else:
                raise ValueError("QUESTRADE_REFRESH_TOKEN environment variable is required when Secrets Manager is disabled")

        # Validate required configuration
        if not all_tokens:
            raise ValueError("No Questrade tokens found in Secrets Manager or environment variables")
        if not lunchmoney_api_token:
            raise ValueError("LUNCHMONEY_API_TOKEN environment variable is required")

        # Parse asset ID if provided
        asset_id = int(asset_id_str) if asset_id_str else None

        # Extract account IDs from the tokens dictionary keys
        account_ids = list(all_tokens.keys())
        logger.info(f"Starting sync for {len(account_ids)} Questrade account(s): {', '.join(account_ids)}")
        logger.info(f"Syncing last {days_back} days")

        # Initialize Lunch Money client (shared across all accounts)
        lunchmoney_client = LunchMoneyClient(lunchmoney_api_token)

        # Track all results and updated tokens
        all_results = {}
        updated_tokens = {}
        total_new = 0
        total_skipped = 0

        # Process each account individually
        for account_id in account_ids:
            refresh_token = all_tokens[account_id]

            logger.info(f"Processing account {account_id}")

            # Initialize Questrade client for this account
            questrade_client = QuestradeClient(refresh_token)

            # Initialize sync handler
            sync_handler = TransactionSync(
                questrade_client=questrade_client,
                lunchmoney_client=lunchmoney_client,
                asset_id=asset_id
            )

            # Perform sync for this single account
            new_count, skipped_count = sync_handler.sync_account(
                account_id=account_id,
                days_back=days_back
            )

            # Store results
            all_results[account_id] = (new_count, skipped_count)
            total_new += new_count
            total_skipped += skipped_count

            # Check if token was updated
            new_token = questrade_client.get_current_refresh_token()
            if new_token != refresh_token:
                updated_tokens[account_id] = new_token
                logger.info(f"Token updated for account {account_id}")

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
                merged_tokens = {**all_tokens, **updated_tokens}
                tokens_json = json.dumps(merged_tokens)

                logger.info(f"Updating Secrets Manager secret: {secret_name}")
                tokens_updated = update_secret(secret_name, tokens_json)

                if tokens_updated:
                    logger.info("✅ Successfully updated Questrade refresh tokens in Secrets Manager")
                    for account_id in updated_tokens.keys():
                        logger.info(f"  - Updated token for account: {account_id}")
                else:
                    logger.error("❌ Failed to update Questrade refresh tokens in Secrets Manager")
                    logger.warning("Manual update required for tokens:")
                    for account_id, token_value in updated_tokens.items():
                        logger.warning(f"  - Account {account_id}: {token_value[:10]}...")
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
                'accounts_processed': len(account_ids),
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
