import asyncio
import json
import os
import requests

from near_lake_framework import near_primitives, LakeConfig, streamer


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

def valdiate_event_data(event_data: dict) -> bool:
    expected_keys = ["foreign_chain_id", "signed_transactions"]
    has_all_necessary_keys = all(exp_key in event_data for exp_key in expected_keys)
    return has_all_necessary_keys and len(event_data.get("signed_transactions", [])) == 2


async def handle_streamer_message(streamer_message: near_primitives.StreamerMessage):
    for shard in streamer_message.shards:
        for receipt_execution_outcome in shard.receipt_execution_outcomes:
            for log in receipt_execution_outcome.execution_outcome.outcome.logs:
                if not log.startswith("EVENT_JSON:"):
                    continue
                try:
                    parsed_log = json.loads(log[len("EVENT_JSON:"):])
                except json.JSONDecodeError:
                    print(
                        f"Receipt ID: `{receipt_execution_outcome.receipt.receipt_id}`\n"
                        f"Error during parsing logs from JSON string to dict"
                    )
                    continue

                if (
                        parsed_log.get("standard") != "x-gas-station"
                        or parsed_log.get("event") != "transaction_sequence_signed"
                ):
                    continue
                else:
                    print(json.dumps(parsed_log, indent=4))

                if receipt_execution_outcome.receipt.receiver_id.endswith(
                        "canhazgas.testnet"
                ):  # TODO load addresses from config
                    try:
                        parsed_event_data = json.loads(parsed_log["data"])
                        if not valdiate_event_data(parsed_event_data):
                            print(f"Invalid event data: {parsed_event_data}")
                        else:
                            payload = {
                                "foreign_chain_id": parsed_event_data["foreign_chain_id"],
                                "raw_transactions": parsed_event_data["signed_transactions"],
                            }
                            requests.post(
                                url="localhost:3030/send_funding_and_user_signed_txns",
                                json=payload,
                            )
                    except json.JSONDecodeError:
                        print(
                            f"Receipt ID: `{receipt_execution_outcome.receipt.receipt_id}`\n"
                            f"Error during parsing event data from JSON string to dict"
                        )
                        continue

                else:
                    continue

                print(json.dumps(parsed_event_data, indent=4))


async def main():
    # TODO change this to the latest block height and mainnet/testnet from config
    config = LakeConfig.testnet()
    config.start_block_height = 157263285
    config.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    config.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    stream_handle, streamer_messages_queue = streamer(config)
    while True:
        streamer_message = await streamer_messages_queue.get()
        await handle_streamer_message(streamer_message)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
