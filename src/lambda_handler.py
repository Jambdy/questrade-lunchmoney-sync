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
        QUESTRADE_SECRET_NAME: Name of Secrets Manager secret for Questrade token (optional)
        USE_SECRETS_MANAGER: Whether to use Secrets Manager (default: 'true')
        QUESTRADE_REFRESH_TOKEN: Questrade OAuth refresh token (fallback if Secrets Manager not used)
        LUNCHMONEY_API_TOKEN: Lunch Money API access token
        QUESTRADE_ACCOUNT_IDS: Comma-separated list of Questrade account IDs
        SYNC_DAYS_BACK: Number of days to sync (default: 31, max: 31)
        LUNCHMONEY_ASSET_ID: Optional Lunch Money asset ID to associate transactions

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Response dictionary with status and results
    """
    try:
        # Get configuration from environment variables
        use_secrets_manager = os.environ.get('USE_SECRETS_MANAGER', 'true').lower() == 'true'
        secret_name = os.environ.get('QUESTRADE_SECRET_NAME', 'questrade-lunchmoney/questrade-token')
        lunchmoney_api_token = os.environ.get('LUNCHMONEY_API_TOKEN')
        account_ids_str = os.environ.get('QUESTRADE_ACCOUNT_IDS', '')
        days_back = int(os.environ.get('SYNC_DAYS_BACK', '31'))
        asset_id_str = os.environ.get('LUNCHMONEY_ASSET_ID')

        # Get Questrade refresh token from Secrets Manager or environment variable
        questrade_refresh_token = None
        if use_secrets_manager:
            logger.info(f"Retrieving Questrade refresh token from Secrets Manager: {secret_name}")
            questrade_refresh_token = get_secret(secret_name)

        # Fallback to environment variable if Secrets Manager not used or failed
        if not questrade_refresh_token:
            logger.info("Falling back to environment variable for Questrade refresh token")
            questrade_refresh_token = os.environ.get('QUESTRADE_REFRESH_TOKEN')

        # Validate required configuration
        if not questrade_refresh_token:
            raise ValueError("QUESTRADE_REFRESH_TOKEN not found in Secrets Manager or environment variables")
        if not lunchmoney_api_token:
            raise ValueError("LUNCHMONEY_API_TOKEN environment variable is required")
        if not account_ids_str:
            raise ValueError("QUESTRADE_ACCOUNT_IDS environment variable is required")

        # Parse account IDs
        account_ids = [aid.strip() for aid in account_ids_str.split(',') if aid.strip()]
        if not account_ids:
            raise ValueError("At least one account ID must be provided in QUESTRADE_ACCOUNT_IDS")

        # Parse asset ID if provided
        asset_id = int(asset_id_str) if asset_id_str else None

        logger.info(f"Starting sync for {len(account_ids)} account(s)")
        logger.info(f"Syncing last {days_back} days")

        # Initialize clients
        questrade_client = QuestradeClient(questrade_refresh_token)
        lunchmoney_client = LunchMoneyClient(lunchmoney_api_token)

        # Initialize sync handler
        sync_handler = TransactionSync(
            questrade_client=questrade_client,
            lunchmoney_client=lunchmoney_client,
            asset_id=asset_id
        )

        # Perform sync
        results = sync_handler.sync_multiple_accounts(
            account_ids=account_ids,
            days_back=days_back
        )

        # Calculate totals
        total_new = sum(new for new, _ in results.values())
        total_skipped = sum(skipped for _, skipped in results.values())

        # Log results
        logger.info(f"Sync completed: {total_new} new transactions, {total_skipped} duplicates skipped")
        for account_id, (new_count, skipped_count) in results.items():
            logger.info(f"  Account {account_id}: {new_count} new, {skipped_count} skipped")

        # Update refresh token if it changed
        new_refresh_token = questrade_client.get_current_refresh_token()
        token_updated = False
        if new_refresh_token != questrade_refresh_token:
            logger.info("Questrade refresh token has been updated")

            # Automatically update Secrets Manager if enabled
            if use_secrets_manager:
                logger.info(f"Updating Secrets Manager secret: {secret_name}")
                token_updated = update_secret(secret_name, new_refresh_token)
                if token_updated:
                    logger.info("✅ Successfully updated Questrade refresh token in Secrets Manager")
                else:
                    logger.error("❌ Failed to update Questrade refresh token in Secrets Manager")
                    logger.warning(f"Manual update required. New token: {new_refresh_token[:10]}...")
            else:
                logger.warning(
                    "Secrets Manager not enabled. "
                    "Please manually update your QUESTRADE_REFRESH_TOKEN environment variable with: "
                    f"{new_refresh_token}"
                )

        return {
            'statusCode': 200,
            'body': {
                'message': 'Sync completed successfully',
                'results': {
                    account_id: {
                        'new_transactions': new_count,
                        'skipped_duplicates': skipped_count
                    }
                    for account_id, (new_count, skipped_count) in results.items()
                },
                'totals': {
                    'new_transactions': total_new,
                    'skipped_duplicates': total_skipped
                },
                'token_rotated': new_refresh_token != questrade_refresh_token,
                'token_auto_updated': token_updated,
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
