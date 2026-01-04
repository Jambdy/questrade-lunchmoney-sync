import os
import logging
from typing import Dict, Any
from .questrade import QuestradeClient
from .lunchmoney import LunchMoneyClient
from .sync import TransactionSync

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function for syncing Questrade to Lunch Money.

    Environment Variables Required:
        QUESTRADE_REFRESH_TOKEN: Questrade OAuth refresh token
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
        questrade_refresh_token = os.environ.get('QUESTRADE_REFRESH_TOKEN')
        lunchmoney_api_token = os.environ.get('LUNCHMONEY_API_TOKEN')
        account_ids_str = os.environ.get('QUESTRADE_ACCOUNT_IDS', '')
        days_back = int(os.environ.get('SYNC_DAYS_BACK', '31'))
        asset_id_str = os.environ.get('LUNCHMONEY_ASSET_ID')

        # Validate required environment variables
        if not questrade_refresh_token:
            raise ValueError("QUESTRADE_REFRESH_TOKEN environment variable is required")
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
        if new_refresh_token != questrade_refresh_token:
            logger.warning(
                "Questrade refresh token has been updated. "
                "Please update your QUESTRADE_REFRESH_TOKEN environment variable with: "
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
                'new_refresh_token': new_refresh_token if new_refresh_token != questrade_refresh_token else None
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
