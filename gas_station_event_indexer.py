from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, fields
from typing import Optional, Any

import requests
import toml
from dataclasses_json import DataClassJsonMixin
from near_lake_framework import near_primitives, LakeConfig, streamer, Network

REQUEST_TIMEOUT = 10
ParsedLog = dict[str, Any]


@dataclass
class EventData(DataClassJsonMixin):
    """
    {
      "foreign_chain_id": "97",
      "sender_local_address": "hatchet.testnet",
      "signed_transactions": [
        "f862037882520894c5acb93d901fb260359cd1e982998236cfac65e0834ce7808002a02dfe84af26b45fec8704a6542e828428fcce018a4e266e19e087a55f1f73fff8a06cc72dc5ecc66c84e3b4f02513961235fff5f463ac68fd00f5072a6f64bfe4cc",
        "f85f8078825208940505050505050505050505050505050505050505648003a033d5ef8c991ec82b9a6b38b7f7ca91ba34ec814c9eec1e2a42e4fc4fc9c443f7a0675e56a82d9464d1cba7ef62d7b9d6e1a4b87328c610b28dfc4b81815f8969d0"
      ]
    }
    """

    foreign_chain_id: str
    sender_local_address: str
    signed_transactions: list[str]

    def validate(self) -> bool:
        return len(self.signed_transactions) == 2

    def send_to_service(self) -> None:
        payload = {
            "foreign_chain_id": self.foreign_chain_id,
            "signed_transactions": self.signed_transactions,
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


@dataclass
class Config:
    """
    Runtime Configuration class
    """

    network: Network
    contract_id: str

    @staticmethod
    def from_toml(config_path: str = "config.toml") -> Config:
        config_dict = toml.load(config_path)
        required_keys = {field.name for field in fields(Config)}
        if not all(key in config_dict for key in required_keys):
            missing_keys = required_keys - config_dict.keys()
            raise ValueError(f"Missing keys in {config_path}: {missing_keys}")

        config_dict["network"] = Network.from_string(config_dict["network"])
        return Config(**config_dict)


def fetch_latest_block(
    network: Network = Network.MAINNET,
) -> near_primitives.BlockHeight:
    """
    Define the RPC endpoint for the NEAR network
    """
    url = f"https://rpc.{network}.near.org"

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
    latest_final_block: int = response.json()["result"]["header"]["height"]

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


def extract_relevant_log(
    log: str, receipt_id: near_primitives.CryptoHash
) -> Optional[ParsedLog]:
    log_key = "EVENT_JSON:"
    if not log.startswith(log_key):
        return None

    try:
        parsed_log: ParsedLog = json.loads(log[len(log_key) :])
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


def process_shard(shard: near_primitives.IndexerShard) -> None:
    for receipt_execution_outcome in shard.receipt_execution_outcomes:
        process_receipt_execution_outcome(receipt_execution_outcome)


def process_receipt_execution_outcome(
    receipt_execution_outcome: near_primitives.IndexerExecutionOutcomeWithReceipt,
) -> None:
    for log in receipt_execution_outcome.execution_outcome.outcome.logs:
        receipt = receipt_execution_outcome.receipt
        if not process_log(log, receipt):
            continue


def process_log(log: str, receipt: near_primitives.Receipt) -> bool:
    parsed_log = extract_relevant_log(log, receipt.receipt_id)
    if parsed_log is None:
        return False

    print(json.dumps(parsed_log, indent=4))
    return process_receipt_if_gas_station_contract(receipt, parsed_log)


def process_receipt_if_gas_station_contract(
    receipt: near_primitives.Receipt, parsed_log: ParsedLog
) -> bool:
    if not receipt.receiver_id.endswith(CONFIG.contract_id):
        return False

    try:
        event_data = EventData.from_dict(parsed_log["data"])
        if not event_data.validate():
            print(f"Error: Invalid event data: {event_data}")
            return False

        print(json.dumps(event_data, indent=4))
        event_data.send_to_service()
        return True

    except json.JSONDecodeError:
        print(
            f"Receipt ID: `{receipt.receipt_id}`\n"
            "Error during parsing event data from JSON string to dict"
        )
        return False


async def handle_streamer_message(
    streamer_message: near_primitives.StreamerMessage,
) -> None:
    for shard in streamer_message.shards:
        process_shard(shard)


async def main() -> None:
    latest_final_block = fetch_latest_block(network=CONFIG.network)
    lake_config = LakeConfig(
        network=CONFIG.network,
        start_block_height=latest_final_block,
        # These fields must be set!
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    print(f"Latest final block: {latest_final_block} on network: {CONFIG.network}")

    _stream_handle, streamer_messages_queue = streamer(lake_config)
    while True:
        streamer_message = await streamer_messages_queue.get()
        await handle_streamer_message(streamer_message)


CONFIG = Config.from_toml()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main())
