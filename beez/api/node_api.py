"""The nodes API to get and post information from and to the Beez blockchain."""
from __future__ import annotations
import os
import time
import json
from typing import TYPE_CHECKING
from flask_classful import FlaskView, route  # type:ignore
from flask import Flask, jsonify, request, send_file
from waitress import serve
from loguru import logger
from whoosh.fields import Schema, TEXT, KEYWORD, ID  # type: ignore
from dotenv import load_dotenv
from beez.beez_utils import BeezUtils

from beez.index.index_engine import (
    TxIndexEngine,
    TxpIndexEngine,
    BlockIndexEngine,
)

load_dotenv()  # load .env

NODE_API_PORT = os.environ.get("NODE_API_PORT", default=8176)
NODE_DAM_FOLDER = os.environ.get("NODE_DAM_FOLDER", default="/assets/")

if TYPE_CHECKING:
    from beez.node.beez_node import BeezNode
    from beez.types import Address
    from beez.transaction.transaction import Transaction
    from beez.transaction.challenge_tx import ChallengeTX

BEEZ_NODE = None


class BaseNodeAPI(FlaskView):
    """Base class for Beez Nodes REST API interface."""

    def __init__(self) -> None:
        self.app = Flask(__name__)
        if not os.path.isdir(NODE_DAM_FOLDER):
            oldmask = os.umask(000)
            os.makedirs(NODE_DAM_FOLDER, 777, exist_ok=True)
            os.umask(oldmask)
        self.app.config['UPLOAD_FOLDER'] = NODE_DAM_FOLDER
        self.app.config['MAX_CONTENT_LENGTH'] = 2 * 1000 * 1000 * 1000  # limit upload size to 2gb

    # find a way to use the properties of the node in the nodeAPI
    def inject_node(self, incjected_node: BeezNode) -> None:
        """Inject the node object of this Blockchain instance and make it
        available for the endpoints."""
        global BEEZ_NODE  # pylint: disable=global-statement
        BEEZ_NODE = incjected_node


class SeedNodeAPI(BaseNodeAPI):
    """Beez Seed Node REST API interface."""

    def start(self, node_ip: Address, port=None) -> None:
        """Starts the REST API."""
        logger.info(f"Seed Node API started at {node_ip}:{NODE_API_PORT}")
        SeedNodeAPI.register(self.app, route_base="/")
        serve(self.app, host=node_ip, port=port if port else NODE_API_PORT)

    @route("/clusterhealth", methods=["GET"])
    def cluster_health(self):
        """Returns the node's connected nodes."""
        cluster_health = BEEZ_NODE.p2p.node_health_status
        return {"cluster_health": cluster_health}, 200
    
    @route("/uploadasset", methods=["POST"])
    def upload_asset(self):
        """Upload a new asset."""

        # 1. Has to contain valid upload asset transaction

        if 'transaction' not in request.files:
            print("transaction is missing")
            return "Missing transaction", 400
        
        transaction = request.files["transaction"]

        transaction.save("/tmp/transaction.json")
        with open("/tmp/transaction.json") as infile:
            tx = json.load(infile)
            transaction_object: Transaction = BeezUtils.decode(tx["transaction"])

        # 2. Has to contain digital asset
        # check if the post request has the file part
        if 'file' not in request.files:
            logger.info('file missing in request')
            return "Missing file", 400
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        file = request.files['file']
        if file.filename == '':
            logger.info('file has no filname')
            return "Missing file", 400
        
        logger.info(f'Uploaded file {file.filename}')
        
        # 3. Only if the asset is pushed to the storage nodes successfully, the upload asset transaction is sent
        if file:
            filename = file.filename
            file.save(os.path.join(self.app.config['UPLOAD_FOLDER'], filename))
            content = b''
            with open(os.path.join(self.app.config['UPLOAD_FOLDER'], filename), 'rb') as infile:
                content = infile.read()
            if content != b'':
                BEEZ_NODE.process_uploaded_asset(filename, content)
                asset_hash = BeezUtils.hash(content).hexdigest()
                for _ in range(60):
                    time.sleep(1)
                    all_acknowledged = True
                    acknowledged_chunks = 0
                    for chunk_id in list(BEEZ_NODE.pending_chunks[asset_hash].keys()):
                        if BEEZ_NODE.pending_chunks[asset_hash][chunk_id]["status"] == True:
                            all_acknowledged = False
                        else:
                            acknowledged_chunks += 1
                    if all_acknowledged:
                        BEEZ_NODE.pending_chunks.pop(asset_hash, None)
                        BEEZ_NODE.broadcast_transaction(transaction_object)    # sending transaction to blockchain
                        return f"Uploaded file {filename}", 201
                    else:
                        logger.info(f'Currently acknowledged {acknowledged_chunks}')
                logger.info('Timeout exceeded when trying to upload file')
                BEEZ_NODE.pending_chunks.pop(asset_hash, None)
                return f"Timout exceeded when trying to upload file {filename}", 400
            else:
                logger.info('uploaded file is empty')
                return f"Uploaded file {filename} is empty", 400
        logger.info('Cant upload file')
        return f"Did not upload file", 400
        
    @route("/downloadasset", methods=["POST"])
    def download_asset(self):
        """Download an asset."""
        values = request.get_json()

        if not "filename" in values:
            return "Missing filename", 400

        file_content = BEEZ_NODE.get_distributed_asset(values["filename"])
        with open("/tmp/testtext.txt", 'w+b') as outfile:
            outfile.write(file_content)

        
        # return {"file_content": file_content.decode()}, 201
    
        try:
            return send_file("/tmp/testtext.txt", attachment_filename="testtext.txt")
            # return send_file(os.path.join(self.app.config['UPLOAD_FOLDER'], values["filename"]), attachment_filename=values["filename"])
        except Exception as e:
            return str(e)

    


class NodeAPI(BaseNodeAPI):
    """NodeAPI class which represents the HTTP communication interface."""

    def start(self, node_ip: Address, port=None) -> None:
        """Starts the REST API."""
        logger.info(f"Node API started at {node_ip}:{NODE_API_PORT}")
        NodeAPI.register(self.app, route_base="/")
        serve(self.app, host=node_ip, port=port if port else NODE_API_PORT)

    @route("/txpindex", methods=["GET"])
    def txpindex(self) -> tuple[str, int]:
        """Returns the current state of the transaction pool"""
        logger.info("Fetching indexed transactionpool transactions")
        fields_to_search = ["id", "type", "txp_encoded"]

        for query in ["TXP"]:
            print(f"Query:: {query}")
            print(
                "\t",
                TxpIndexEngine.get_engine(
                    Schema(
                        id=ID(stored=True),
                        type=KEYWORD(stored=True),
                        txp_encoded=TEXT(stored=True),
                    )
                ).query(query, fields_to_search, highlight=True),
            )
            print("-" * 70)

        txp_index_str = str(
            TxpIndexEngine.get_engine(
                Schema(
                    id=ID(stored=True),
                    type=KEYWORD(stored=True),
                    txp_encoded=TEXT(stored=True),
                )
            ).query(query, fields_to_search, highlight=True)
        )

        return txp_index_str, 200

    @route("/txindex", methods=["GET"])
    def txindex(self):
        """Returns the current state of the transactions."""
        logger.info("Fetching indexed transaction")
        fields_to_search = ["id", "type", "tx_encoded"]

        for query in ["TX"]:
            print(f"Query:: {query}")
            print(
                "\t",
                TxIndexEngine.get_engine(
                    Schema(
                        id=ID(stored=True),
                        type=KEYWORD(stored=True),
                        tx_encoded=TEXT(stored=True),
                    )
                ).query(query, fields_to_search, highlight=True),
            )
            print("-" * 70)

        tx_index_str = str(
            TxIndexEngine.get_engine(
                Schema(
                    id=ID(stored=True),
                    type=KEYWORD(stored=True),
                    tx_encoded=TEXT(stored=True),
                )
            ).query(query, fields_to_search, highlight=True)
        )

        return tx_index_str, 200

    @route("/blockindex", methods=["GET"])
    def blockindex(self):
        """Returns the current state of the blocks."""
        logger.info("Checking indexed blocks")
        fields_to_search = ["id", "type", "block_serialized"]

        for query in ["BL"]:
            print(f"Query:: {query}")
            print(
                "\t",
                BlockIndexEngine.get_engine(
                    Schema(
                        id=ID(stored=True),
                        type=KEYWORD(stored=True),
                        block_encoded=TEXT(stored=True),
                    )
                ).query(query, fields_to_search, highlight=True),
            )
            print("-" * 70)

            resultsset = []
            blocks = BEEZ_NODE.blockchain.blocks_from_index()
            for block in blocks:
                resultsset.append(block.serialize())

        return str(resultsset), 200

    @route("/info", methods=["GET"])
    def info(self):
        """Returns general information about the Beez blockchain."""
        logger.info("Provide some info about the Blockchain")
        return "This is Beez Blockchain!. 🦾 🐝 🐝 🐝 🦾", 200

    @route("/transaction", methods=["POST"])
    def transaction(self):
        """Post a transaction to the blockchain."""
        values = request.get_json()  # we aspect to receive json objects!

        if not "transaction" in values:
            return "Missing transaction value", 400

        transaction: Transaction = BeezUtils.decode(values["transaction"])

        # manage the transaction on the Blockchain
        BEEZ_NODE.handle_transaction(transaction)

        response = {"message": "Received transaction"}

        return jsonify(response), 201

    @route("/challenge", methods=["POST"])
    def challenge(self):
        """Post a challenge to the blockchain."""
        values = request.get_json()  # we aspect to receive json objects!

        if not "challenge" in values:
            return "Missing challenge value", 400

        transaction: ChallengeTX = BeezUtils.decode(values["challenge"])

        # manage the transaction on the Blockchain
        BEEZ_NODE.handle_challenge_tx(transaction)

        response = {"message": "Received challenge"}

        return jsonify(response), 201

    @route("/transactionpool", methods=["GET"])
    def transaction_pool(self):
        """Returns the current state of the in-memory transaction pool"""
        # Implement this
        logger.info("Send all the transactions that are on the transaction pool")
        transactions = {}

        # logger.info(f"Transactions: {node.transactionPool.transactions}")

        for idx, transaction in enumerate(BEEZ_NODE.transaction_pool.transactions):
            logger.info(f"Transaction: {idx} : {transaction.id}")
            transactions[idx] = transaction.toJson()

        # logger.info(f"Transactions to Json: {transactions}")

        return jsonify(transactions), 200

    @route("/accountstatemodel", methods=["GET"])
    def account_state_model(self):
        """Returns the current state of the account_state_model"""
        # Implement this
        logger.info("Send the current account_state_model state")

        # logger.info(f"Transactions to Json: {transactions}")

        return jsonify(BEEZ_NODE.blockchain.account_state_model.serialize()), 200

    # @route("/challenges", methods=['GET'])
    # def challenges(self):
    #     # Implement this
    #     logger.info(
    #         f"Send all the challenges that are on the BeezKeeper")

    #     json_challenges = {}

    #     # json_challenges = json.dumps(BEEZ_NODE.beezKeeper.challenges)

    #     challenges = BEEZ_NODE.blockchain.beezKeeper.challenges

    #     for challengeID, challengeTx in challenges.items():
    #         cTx : ChallengeTX = challengeTx

    #         # logger.info(f"{cTx.toJson()}")
    #         json_challenges[challengeID] = cTx.toJson()

    #     # logger.info(f"Challenges: {BEEZ_NODE.beezKeeper.challenges}")

    #     return jsonify(json_challenges), 200

    @route("/blockchain", methods=["GET"])
    def blockchain(self):
        """Returns the state of the in-memory blockchain."""
        logger.info("Blockchain called...")
        return BEEZ_NODE.blockchain.to_json(), 200

    @route("/registeraddress", methods=["POST", "OPTIONS"])
    def register_address(self):
        """Post a new address to public-key mapping."""
        values = request.get_json()  # we aspect to receive json objects!

        if not "publickey" in values:
            return "Missing public-key value", 400

        # manage the transaction on the Blockchain
        beez_address = BEEZ_NODE.handle_address_registration(values["publickey"])
        return_string = f"Added {beez_address}: {values['publickey']}"

        response = {"message": return_string}

        return jsonify(response), 201

    @route("/registeredaddresses", methods=["GET"])
    def registered_addresses(self):
        """Returns the registered addresses of this node."""
        registered_addresses = BEEZ_NODE.get_registered_addresses()
        return {"registered_addresses": registered_addresses}, 200

    @route("/connectednodes", methods=["GET"])
    def connected_nodes(self):
        """Returns the node's connected nodes."""
        connected_nodes = BEEZ_NODE.p2p.own_connections
        connections: dict[str:int] = {}
        for connected_node in connected_nodes:
            connections[connected_node.ip_address] = connected_node.port
        if BEEZ_NODE.p2p.neighbor:
            connections[
                BEEZ_NODE.p2p.neighbor.ip_address
            ] = f"{BEEZ_NODE.p2p.neighbor.port} -- Neighbor"
        return {"connected_nodes": connections}, 200
