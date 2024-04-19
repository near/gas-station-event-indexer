# gas-station-event-indexer
Picks up events emitted from the gas station contract used for generating signed foreign chain transactions and calls the multichain relayer `/send_funding_and_user_signed_txns` endpoint locally

# Run
1. ensure you have https://github.com/near/multichain-relayer-server running on localhost:3030
2. update the config.toml with the appropriate values
3. `make run` - this will create a virtual environment, install dependencies and run `gas_station_event_indexer.py`
