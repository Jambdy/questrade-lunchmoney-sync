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
        QUESTRADE_SECRET_NAME: Name of Secrets Manager secret for Questrade account configs
        USE_SECRETS_MANAGER: Whether to use Secrets Manager (default: 'true')
        LUNCHMONEY_API_TOKEN: Lunch Money API access token
        SYNC_DAYS_BACK: Number of days to sync (default: 31, max: 31)

    Secrets Manager format (JSON):
        {
          "accounts": [
            {
              "questrade_account_id": "12345678",
              "questrade_refresh_token": "your-questrade-refresh-token-here",
              "lunchmoney_asset_name": "Questrade - Account Name - RRSP"
            }
          ]
        }

    The asset names are used to look up the corresponding asset IDs in Lunch Money.
    Each account has its own Questrade token and is linked to a specific Lunch Money asset.

    Args:
        event: Lambda event object
        context: Lambda context object

    Returns:
        Response dictionary with status and results
    """
    try:
        # Get configuration from environment variables
        use_secrets_manager = os.environ.get('USE_SECRETS_MANAGER', 'true').lower() == 'true'
        secret_name = os.environ.get('QUESTRADE_SECRET_NAME', 'questrade-lunchmoney/account-configs')
        lunchmoney_api_token = os.environ.get('LUNCHMONEY_API_TOKEN')
        days_back = int(os.environ.get('SYNC_DAYS_BACK', '31'))

        # Get account configurations from Secrets Manager
        account_configs = []
        if use_secrets_manager:
            logger.info(f"Retrieving account configurations from Secrets Manager: {secret_name}")
            config_json = get_secret(secret_name)
            if config_json:
                try:
                    config_data = json.loads(config_json)
                    account_configs = config_data.get('accounts', [])
                    logger.info(f"Loaded configurations for {len(account_configs)} Questrade account(s) from Secrets Manager")
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in Secrets Manager secret {secret_name}: {str(e)}")
            else:
                raise ValueError(f"Could not retrieve secret {secret_name} from Secrets Manager")
        else:
            # Fallback to environment variable if Secrets Manager not enabled
            logger.info("Secrets Manager disabled, falling back to QUESTRADE_ACCOUNT_CONFIGS environment variable")
            config_env = os.environ.get('QUESTRADE_ACCOUNT_CONFIGS', '')
            if config_env:
                try:
                    config_data = json.loads(config_env)
                    account_configs = config_data.get('accounts', [])
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in QUESTRADE_ACCOUNT_CONFIGS: {str(e)}")
            else:
                raise ValueError("QUESTRADE_ACCOUNT_CONFIGS environment variable is required when Secrets Manager is disabled")

        # Validate required configuration
        if not account_configs:
            raise ValueError("No Questrade account configurations found in Secrets Manager or environment variables")
        if not lunchmoney_api_token:
            raise ValueError("LUNCHMONEY_API_TOKEN environment variable is required")

        logger.info(f"Starting sync for {len(account_configs)} Questrade account(s)")
        logger.info(f"Syncing last {days_back} days")

        # Initialize Lunch Money client (shared across all accounts)
        lunchmoney_client = LunchMoneyClient(lunchmoney_api_token)

        # Track all results and updated configs
        all_results = {}
        updated_configs = []
        total_new = 0
        total_skipped = 0

        # Process each account individually
        for account_config in account_configs:
            questrade_account_id = account_config.get('questrade_account_id')
            refresh_token = account_config.get('questrade_refresh_token')
            lunchmoney_asset_name = account_config.get('lunchmoney_asset_name')

            # Validate account config
            if not questrade_account_id or not refresh_token or not lunchmoney_asset_name:
                logger.error(f"Invalid account config: {account_config}")
                continue

            logger.info(f"Processing Questrade account {questrade_account_id} → Lunch Money asset '{lunchmoney_asset_name}'")

            # Look up Lunch Money asset ID by name
            logger.info(f"Looking up Lunch Money asset: {lunchmoney_asset_name}")
            asset = lunchmoney_client.get_asset_by_name(lunchmoney_asset_name)
            if not asset:
                logger.error(f"Lunch Money asset '{lunchmoney_asset_name}' not found. Skipping account {questrade_account_id}.")
                all_results[questrade_account_id] = (0, 0)
                continue

            asset_id = asset.get('id')
            logger.info(f"Found Lunch Money asset ID: {asset_id}")

            # Initialize Questrade client for this account
            questrade_client = QuestradeClient(refresh_token)

            # Initialize sync handler
            sync_handler = TransactionSync(
                questrade_client=questrade_client,
                lunchmoney_client=lunchmoney_client,
                asset_id=asset_id
            )

            # Perform sync for this single account
            try:
                new_count, skipped_count = sync_handler.sync_account(
                    account_id=questrade_account_id,
                    days_back=days_back
                )

                # Store results
                all_results[questrade_account_id] = (new_count, skipped_count)
                total_new += new_count
                total_skipped += skipped_count
            except Exception as sync_error:
                logger.error(f"Sync failed for account {questrade_account_id}: {sync_error}")
                all_results[questrade_account_id] = (0, 0)
                # Continue to save token even if sync failed

            # Check if token was updated (do this even if sync failed)
            new_token = questrade_client.get_current_refresh_token()
            if new_token != refresh_token:
                logger.info(f"Token updated for account {questrade_account_id}")
                # Store updated config
                updated_configs.append({
                    'questrade_account_id': questrade_account_id,
                    'questrade_refresh_token': new_token,
                    'lunchmoney_asset_name': lunchmoney_asset_name
                })
            else:
                # Keep existing config
                updated_configs.append(account_config)

        # Log results
        logger.info(f"Sync completed: {total_new} new transactions, {total_skipped} duplicates skipped")
        for account_id, (new_count, skipped_count) in all_results.items():
            logger.info(f"  Account {account_id}: {new_count} new, {skipped_count} skipped")

        # Update account configurations if any tokens changed
        configs_updated = False
        tokens_changed = len([cfg for cfg in updated_configs if cfg.get('questrade_refresh_token') !=
                             next((orig['questrade_refresh_token'] for orig in account_configs
                                  if orig['questrade_account_id'] == cfg['questrade_account_id']), None)])

        if tokens_changed > 0:
            logger.info(f"{tokens_changed} Questrade token(s) updated")

            # Automatically update Secrets Manager if enabled
            if use_secrets_manager:
                # Create updated config JSON
                updated_config_json = json.dumps({'accounts': updated_configs})

                logger.info(f"Updating Secrets Manager secret: {secret_name}")
                configs_updated = update_secret(secret_name, updated_config_json)

                if configs_updated:
                    logger.info("✅ Successfully updated account configurations in Secrets Manager")
                    for config in updated_configs:
                        # Check if this token was updated
                        original = next((orig for orig in account_configs
                                       if orig['questrade_account_id'] == config['questrade_account_id']), None)
                        if original and original.get('questrade_refresh_token') != config.get('questrade_refresh_token'):
                            logger.info(f"  - Updated token for account: {config['questrade_account_id']}")
                else:
                    logger.error("❌ Failed to update account configurations in Secrets Manager")
                    logger.warning("Manual update required. Updated configuration:")
                    logger.warning(json.dumps({'accounts': updated_configs}, indent=2))
            else:
                logger.warning("Secrets Manager not enabled.")
                logger.warning("Please manually update your QUESTRADE_ACCOUNT_CONFIGS with:")
                logger.warning(json.dumps({'accounts': updated_configs}, indent=2))

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
                'accounts_processed': len(account_configs),
                'tokens_rotated': tokens_changed,
                'configs_auto_updated': configs_updated,
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
