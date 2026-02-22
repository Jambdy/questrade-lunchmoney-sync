import os
import logging
import json
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError
from .questrade import QuestradeClient
from .lunchmoney import LunchMoneyClient

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
ssm_client = boto3.client('ssm')

PARAMETER_NAME = os.environ.get('QUESTRADE_PARAMETER_NAME', '/questrade-lunchmoney/account-configs')


def get_account_configs() -> list:
    """Retrieve account configurations from SSM Parameter Store."""
    try:
        response = ssm_client.get_parameter(Name=PARAMETER_NAME, WithDecryption=True)
        config_data = json.loads(response['Parameter']['Value'])
        accounts = config_data.get('accounts', [])
        logger.info(f"Loaded configurations for {len(accounts)} Questrade account(s) from SSM Parameter Store")
        return accounts
    except ClientError as e:
        raise ValueError(f"Failed to retrieve SSM parameter {PARAMETER_NAME}: {e}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in SSM parameter {PARAMETER_NAME}: {e}")


def save_account_configs(accounts: list) -> None:
    """Save updated account configurations back to SSM Parameter Store."""
    try:
        value = json.dumps({'accounts': accounts})
        ssm_client.put_parameter(Name=PARAMETER_NAME, Value=value, Type='SecureString', Overwrite=True)
        logger.info("Successfully updated account configurations in SSM Parameter Store")
    except ClientError as e:
        logger.error(f"Failed to update SSM parameter {PARAMETER_NAME}: {e}")
        logger.warning("Manual update required. Updated configuration:")
        logger.warning(json.dumps({'accounts': accounts}, indent=2))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function for syncing Questrade to Lunch Money.

    Environment Variables Required:
        QUESTRADE_PARAMETER_NAME: SSM Parameter Store path for Questrade account configs
                                  (default: /questrade-lunchmoney/account-configs)
        LUNCHMONEY_API_TOKEN: Lunch Money API access token

    SSM parameter format (JSON, stored as SecureString):
        {
          "accounts": [
            {
              "questrade_account_id": "12345678",
              "questrade_refresh_token": "your-questrade-refresh-token-here",
              "lunchmoney_asset_name": "Questrade - Account Name - RRSP"
            }
          ]
        }
    """
    try:
        lunchmoney_api_token = os.environ.get('LUNCHMONEY_API_TOKEN')
        if not lunchmoney_api_token:
            raise ValueError("LUNCHMONEY_API_TOKEN environment variable is required")

        account_configs = get_account_configs()
        if not account_configs:
            raise ValueError("No Questrade account configurations found in SSM Parameter Store")

        logger.info(f"Starting balance sync for {len(account_configs)} Questrade account(s)")

        lunchmoney_client = LunchMoneyClient(lunchmoney_api_token)

        all_results = {}
        updated_configs = []
        total_new = 0

        for account_config in account_configs:
            questrade_account_id = account_config.get('questrade_account_id')
            refresh_token = account_config.get('questrade_refresh_token')
            lunchmoney_asset_name = account_config.get('lunchmoney_asset_name')

            if not questrade_account_id or not refresh_token or not lunchmoney_asset_name:
                logger.error(f"Invalid account config: {account_config}")
                continue

            logger.info(f"Processing Questrade account {questrade_account_id} → Lunch Money asset '{lunchmoney_asset_name}'")

            asset = lunchmoney_client.get_asset_by_name(lunchmoney_asset_name)
            if not asset:
                logger.error(f"Lunch Money asset '{lunchmoney_asset_name}' not found. Skipping account {questrade_account_id}.")
                all_results[questrade_account_id] = (0, False)
                updated_configs.append(account_config)
                continue

            asset_id = asset.get('id')
            logger.info(f"Found Lunch Money asset ID: {asset_id}")

            questrade_client = QuestradeClient(refresh_token)

            try:
                logger.info(f"Fetching balance for Questrade account {questrade_account_id}")
                balances = questrade_client.get_account_balances(questrade_account_id)
                total_equity = balances.get('totalEquity', 0)

                logger.info(f"Questrade account {questrade_account_id} balance: ${total_equity:,.2f} CAD")

                lunchmoney_client.update_asset_balance(
                    asset_id=asset_id,
                    balance=total_equity,
                    currency='cad'
                )

                logger.info(f"Successfully updated balance for {lunchmoney_asset_name}")
                all_results[questrade_account_id] = (total_equity, True)
                total_new += 1
            except Exception as sync_error:
                logger.error(f"Balance update failed for account {questrade_account_id}: {sync_error}")
                all_results[questrade_account_id] = (0, False)

            # Capture updated refresh token (Questrade rotates it on each auth)
            new_token = questrade_client.get_current_refresh_token()
            if new_token != refresh_token:
                logger.info(f"Token rotated for account {questrade_account_id}")
                updated_configs.append({
                    'questrade_account_id': questrade_account_id,
                    'questrade_refresh_token': new_token,
                    'lunchmoney_asset_name': lunchmoney_asset_name
                })
            else:
                updated_configs.append(account_config)

        logger.info(f"Balance sync completed: {total_new} account(s) updated successfully")
        for account_id, (balance, success) in all_results.items():
            status = "Updated" if success else "Failed"
            logger.info(f"  Account {account_id}: {status} - Balance: ${balance:,.2f}")

        tokens_changed = sum(
            1 for cfg in updated_configs
            if cfg.get('questrade_refresh_token') != next(
                (orig['questrade_refresh_token'] for orig in account_configs
                 if orig['questrade_account_id'] == cfg['questrade_account_id']), None
            )
        )

        if tokens_changed > 0:
            logger.info(f"{tokens_changed} Questrade token(s) rotated, saving to SSM")
            save_account_configs(updated_configs)

        return {
            'statusCode': 200,
            'body': {
                'message': 'Balance sync completed successfully',
                'results': {
                    account_id: {'balance': balance, 'updated': success}
                    for account_id, (balance, success) in all_results.items()
                },
                'totals': {
                    'accounts_updated': total_new,
                    'accounts_failed': len(all_results) - total_new
                },
                'accounts_processed': len(account_configs),
                'tokens_rotated': tokens_changed,
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
