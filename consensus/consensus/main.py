import os
import argparse
from pathlib import Path
import logging
import trio
from dotenv import load_dotenv
from subnet_network.db.database import RocksDB
from subnet_network.hypertensor.chain_functions import Hypertensor, KeypairFrom
from subnet_network.hypertensor.mock.local_chain_functions import LocalMockHypertensor
from subnet_network.utils.hypertensor.subnet_info_tracker import SubnetInfoTracker
from subnet_consensus.consensus import Consensus
import secrets
from libp2p.crypto.ed25519 import create_new_key_pair
from subnet_network.utils.crypto.store_key import get_key_pair
from libp2p.peer.id import ID as PeerID
from substrateinterface import (
    Keypair as SubstrateKeypair,
    KeypairType,
)


load_dotenv(os.path.join(Path.cwd(), ".env"))

PHRASE = os.getenv("PHRASE")


async def main():
    parser = argparse.ArgumentParser(description="Subnet Consensus Node")
    parser.add_argument(
        "--base_path", type=str, default=None, help="Specify custom base path"
    )

    parser.add_argument(
        "--private_key_path",
        type=str,
        default=None,
        help="Path to the private key file. ",
    )

    parser.add_argument(
        "--subnet_id", type=int, default=0, help="Subnet ID this node belongs to. "
    )

    parser.add_argument(
        "--subnet_node_id",
        type=int,
        default=0,
        help="Subnet node ID this node belongs to. ",
    )

    parser.add_argument(
        "--no_blockchain_rpc", action="store_true", help="[Testing] Run with no RPC"
    )

    parser.add_argument(
        "--local_rpc",
        action="store_true",
        help="[Testing] Run in local RPC mode, uses LOCAL_RPC",
    )

    parser.add_argument(
        "--tensor_private_key",
        type=str,
        required=False,
        help="Hypertensor blockchain private key",
    )

    parser.add_argument(
        "--phrase",
        type=str,
        required=False,
        help="Coldkey phrase that controls actions which include funds, such as registering, and staking",
    )

    parser.add_argument(
        "--use_mock_chain",
        action="store_true",
        help="[Testing] Run with mock blockchain as local database",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging level",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("consensus-main")

    # Initialize components
    db_dir = os.path.dirname(args.db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    db = RocksDB(base_path=args.db_path)
    logger.info(f"Initialized database at {args.db_path}")

    if args.private_key_path is None:
        key_pair = create_new_key_pair(secrets.token_bytes(32))
    else:
        key_pair = get_key_pair(args.private_key_path)

    if args.use_mock_chain:
        hypertensor = LocalMockHypertensor(
            subnet_id=args.subnet_id,
            peer_id=PeerID.from_pubkey(key_pair.public_key),
            subnet_node_id=args.subnet_node_id,
            coldkey="",
            hotkey="",
            bootnode_peer_id="",
            client_peer_id="",
            reset_db=True,
            insert_mock_overwatch_node=True,
        )
        logger.info("Using LocalMockHypertensor")
    else:
        if args.local_rpc:
            rpc = os.getenv("LOCAL_RPC")
        else:
            rpc = os.getenv("DEV_RPC")

        if args.phrase is not None:
            hypertensor = Hypertensor(rpc, args.phrase)
            substrate_keypair = SubstrateKeypair.create_from_mnemonic(
                args.phrase, crypto_type=KeypairType.ECDSA
            )
            hotkey = substrate_keypair.ss58_address
            logger.info(f"hotkey: {hotkey}")
        elif args.tensor_private_key is not None:
            hypertensor = Hypertensor(
                rpc, args.tensor_private_key, KeypairFrom.PRIVATE_KEY
            )
            substrate_keypair = SubstrateKeypair.create_from_private_key(
                args.tensor_private_key, crypto_type=KeypairType.ECDSA
            )
            hotkey = substrate_keypair.ss58_address
            logger.info(f"hotkey: {hotkey}")
        else:
            # Default to using PHRASE if no other options are provided
            hypertensor = Hypertensor(rpc, PHRASE)

    termination_event = trio.Event()

    subnet_info_tracker = SubnetInfoTracker(
        termination_event=termination_event,
        subnet_id=args.subnet_id,
        hypertensor=hypertensor,
    )

    consensus_engine = Consensus(
        db=db,
        subnet_id=args.subnet_id,
        subnet_node_id=args.node_id,
        subnet_info_tracker=subnet_info_tracker,
        hypertensor=hypertensor,
        skip_activate_subnet=args.skip_activate,
    )

    logger.info(
        f"Starting consensus compartment for Subnet {args.subnet_id}, Node {args.node_id}"
    )

    async with trio.open_nursery() as nursery:
        nursery.start_soon(subnet_info_tracker.run)
        # Wait a bit for tracker to sync initial data
        await trio.sleep(1)
        nursery.start_soon(consensus_engine._main_loop)


if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        pass
