import asyncio
import json
import os
from typing import Optional
import requests
import toml

from near_lake_framework import near_primitives, LakeConfig, streamer

REQUEST_TIMEOUT = 10

# load the config
with open("config.toml", "r", encoding="utf-8") as file:
    config = toml.load(file)
    expected_config_keys = ["network", "contract_id"]
    has_all_necessary_config_keys = all(
        exp_key in config for exp_key in expected_config_keys
    )
    if not has_all_necessary_config_keys:
        raise ValueError(f"Missing keys in config.toml: {expected_config_keys}")


def fetch_latest_block(network: str = "mainnet"):
    """
    Define the RPC endpoint for the NEAR network
    """
    url = (
        "https://rpc.mainnet.near.org"
        if network == "mainnet"
        else "https://rpc.testnet.near.org"
    )

    # Define the payload for fetching the latest block
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "dontcare",
            "method": "block",
            "params": {"finality": "final"},
        }
    )

    # Define the headers for the HTTP request
    headers = {"Content-Type": "application/json"}

    # Send the HTTP request to the NEAR RPC endpoint
    response = requests.request(
        "POST", url, headers=headers, data=payload, timeout=REQUEST_TIMEOUT
    )

    # Parse the JSON response to get the latest final block height
    latest_final_block = response.json()["result"]["header"]["height"]

    return latest_final_block


# Event format json example:
# {
#     "standard": "x-gas-station",
#     "version": "0.1.0",
#     "event": "transaction_sequence_signed",
#     "data": {
#         "foreign_chain_id": "97",
#         "sender_local_address": "hatchet.testnet",
#         "signed_transactions": [
#             "f862037882520894c5acb93d901fb260359cd1e982998236cfac65e0834ce7808002a02dfe84af26b45fec8704a6542e828428fcce018a4e266e19e087a55f1f73fff8a06cc72dc5ecc66c84e3b4f02513961235fff5f463ac68fd00f5072a6f64bfe4cc",
#             "f85f8078825208940505050505050505050505050505050505050505648003a033d5ef8c991ec82b9a6b38b7f7ca91ba34ec814c9eec1e2a42e4fc4fc9c443f7a0675e56a82d9464d1cba7ef62d7b9d6e1a4b87328c610b28dfc4b81815f8969d0"
#         ]
#     }
# }


def validate_event_data(event_data: dict) -> bool:
    expected_event_keys = ["foreign_chain_id", "signed_transactions"]
    has_all_necessary_event_keys = all(
        exp_key in event_data for exp_key in expected_event_keys
    )
    return (
        has_all_necessary_event_keys
        and len(event_data.get("signed_transactions", [])) == 2
    )


def extract_relevant_log(
    log: str, receipt_id: near_primitives.CryptoHash
) -> Optional[dict]:
    if not log.startswith("EVENT_JSON:"):
        return None

    try:
        parsed_log = json.loads(log[len("EVENT_JSON:") :])
    except json.JSONDecodeError:
        print(
            f"Receipt ID: `{receipt_id}`\n"
            f"Error during parsing logs from JSON string to dict"
        )
        return None

    if (
        parsed_log.get("standard") != "x-gas-station"
        or parsed_log.get("event") != "transaction_sequence_signed"
    ):
        return None
    return parsed_log


def process_shard(shard: near_primitives.IndexerShard):
    for receipt_execution_outcome in shard.receipt_execution_outcomes:
        process_receipt_execution_outcome(receipt_execution_outcome)


def process_receipt_execution_outcome(
    receipt_execution_outcome: near_primitives.IndexerExecutionOutcomeWithReceipt,
):
    for log in receipt_execution_outcome.execution_outcome.outcome.logs:
        receipt = receipt_execution_outcome.receipt
        if not process_log(log, receipt):
            continue


def process_log(log: str, receipt: near_primitives.Receipt):
    parsed_log = extract_relevant_log(log, receipt.receipt_id)
    if parsed_log is None:
        return False

    print(json.dumps(parsed_log, indent=4))
    return process_receipt_if_gas_station_contract(receipt, parsed_log)


def process_receipt_if_gas_station_contract(
    receipt: near_primitives.Receipt, parsed_log: dict
) -> bool:
    if not receipt.receiver_id.endswith(config.get("contract_id")):
        return False

    try:
        parsed_event_data = parsed_log["data"]
        if not validate_event_data(parsed_event_data):
            print(f"Error: Invalid event data: {parsed_event_data}")
            return False

        print(json.dumps(parsed_event_data, indent=4))
        send_event_data_to_service(parsed_event_data)
        return True

    except json.JSONDecodeError:
        print(
            f"Receipt ID: `{receipt.receipt_id}`\nError during parsing event data from JSON string to dict"
        )
        return False


def send_event_data_to_service(event_data: dict):
    payload = {
        "foreign_chain_id": event_data["foreign_chain_id"],
        "signed_transactions": event_data["signed_transactions"],
    }
    url = "localhost:3030/send_funding_and_user_signed_txns"
    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        if response.status_code not in {200, 201}:
            print(f"Error: calling {url}: {response.text}")
        else:
            print(f"Response from {url}: {response.text}")
    except requests.RequestException as e:
        print(f"HTTP Request failed: {str(e)}")


async def handle_streamer_message(streamer_message: near_primitives.StreamerMessage):
    for shard in streamer_message.shards:
        process_shard(shard)
    # for shard in streamer_message.shards:
    #     for receipt_execution_outcome in shard.receipt_execution_outcomes:
    #         for log in receipt_execution_outcome.execution_outcome.outcome.logs:
    #             receipt = receipt_execution_outcome.receipt

    #             parsed_log = extract_relevant_log(log, receipt.receipt_id)
    #             if parsed_log is None:
    #                 continue

    #             print(json.dumps(parsed_log, indent=4))

    #             # gas station contract account id
    #             if receipt.receiver_id.endswith(config.get("contract_id")):
    #                 try:
    #                     parsed_event_data: dict = parsed_log["data"]
    #                     if not valdiate_event_data(parsed_event_data):
    #                         print(f"Error: Invalid event data: {parsed_event_data}")
    #                     else:
    #                         payload = {
    #                             "foreign_chain_id": parsed_event_data["foreign_chain_id"],
    #                             "signed_transactions": parsed_event_data["signed_transactions"],
    #                         }
    #                         url = "localhost:3030/send_funding_and_user_signed_txns"
    #                         response = requests.post(
    #                             url,
    #                             json=payload,
    #                             timeout=REQUEST_TIMEOUT,
    #                         )
    #                         if response.status_code not in {200, 201}:
    #                             print(f"Error: calling {url}: {response.text}")
    #                         else:
    #                             print(f"Response from {url}: {response.text}")
    #                 except json.JSONDecodeError:
    #                     print(
    #                         f"Receipt ID: `{receipt.receipt_id}`\n"
    #                         f"Error during parsing event data from JSON string to dict"
    #                     )
    #                     continue

    #             else:
    #                 continue

    #             print(json.dumps(parsed_event_data, indent=4))


async def main() -> None:
    if config.get("network") == "mainnet":
        lake_config = LakeConfig.mainnet()
        latest_final_block = fetch_latest_block(network="mainnet")
    elif config.get("network") == "testnet":
        lake_config = LakeConfig.testnet()
        latest_final_block = fetch_latest_block(network="testnet")
    else:
        raise ValueError(f"Unknown network: {config.get('network')}")

    print(
        f"Latest final block: {latest_final_block} on network: {config.get('network')}"
    )
    lake_config.start_block_height = latest_final_block
    lake_config.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    lake_config.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    _stream_handle, streamer_messages_queue = streamer(lake_config)
    while True:
        streamer_message = await streamer_messages_queue.get()
        await handle_streamer_message(streamer_message)


loop = asyncio.new_event_loop()
loop.run_until_complete(main())
