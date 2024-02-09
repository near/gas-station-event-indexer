import asyncio
import json
import os
import re

from near_lake_framework import near_primitives, LakeConfig, streamer


def format_paras_nfts(data, receipt_execution_outcome):
    links = []

    for data_element in data:
        for token_id in data_element.get("token_ids", []):
            first_part_of_token_id = token_id.split(":")[0]
            links.append(
                f"https://paras.id/token/{receipt_execution_outcome.receipt.receiver_id}::{first_part_of_token_id}/{token_id}"
            )

    return {"owner": data[0].get("owner_id"), "links": links}


def format_mintbase_nfts(data, receipt_execution_outcome):
    links = []
    for data_block in data:
        try:
            memo = json.loads(data_block.get("memo"))
        except json.JSONDecodeError:
            print(
                f"Receipt ID: `{receipt_execution_outcome.receipt.receipt_id}`\nMemo: `{memo}`\nError during parsing Mintbase memo from JSON string to dict"
            )
            return

        meta_id = memo.get("meta_id")
        links.append(
            f"https://www.mintbase.io/thing/{meta_id}:{receipt_execution_outcome.receipt.receiver_id}"
        )

    return {"owner": data[0].get("owner_id"), "links": links}


async def handle_streamer_message(streamer_message: near_primitives.StreamerMessage):
    for shard in streamer_message.shards:
        for receipt_execution_outcome in shard.receipt_execution_outcomes:
            for log in receipt_execution_outcome.execution_outcome.outcome.logs:
                if not log.startswith("EVENT_JSON:"):
                    continue
                try:
                    parsed_log = json.loads(log[len("EVENT_JSON:") :])
                except json.JSONDecodeError:
                    print(
                        f"Receipt ID: `{receipt_execution_outcome.receipt.receipt_id}`\nError during parsing logs from JSON string to dict"
                    )
                    continue

                if (
                        parsed_log.get("standard") != "nep171"
                        or parsed_log.get("event") != "nft_mint"
                ):
                    continue

                if receipt_execution_outcome.receipt.receiver_id.endswith(
                        ".paras.near"
                ):
                    output = {
                        "receipt_id": receipt_execution_outcome.receipt.receipt_id,
                        "marketplace": "Paras",
                        "nfts": format_paras_nfts(
                            parsed_log["data"], receipt_execution_outcome
                        ),
                    }
                elif re.search(
                        ".mintbase\d+.near", receipt_execution_outcome.receipt.receiver_id
                ):
                    output = {
                        "receipt_id": receipt_execution_outcome.receipt.receipt_id,
                        "marketplace": "Mintbase",
                        "nfts": format_mintbase_nfts(
                            parsed_log["data"], receipt_execution_outcome
                        ),
                    }
                else:
                    continue

                print(json.dumps(output, indent=4))


async def main():
    config = LakeConfig.mainnet()
    config.start_block_height = 69030747
    config.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    config.aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    stream_handle, streamer_messages_queue = streamer(config)
    while True:
        streamer_message = await streamer_messages_queue.get()
        await handle_streamer_message(streamer_message)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())