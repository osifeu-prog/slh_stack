
import os, json
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from web3 import Web3, HTTPProvider
from eth_account import Account

load_dotenv()

app = FastAPI(title="SLH API")

BSC_RPC_URL = os.getenv("BSC_RPC_URL", "https://bsc-testnet-rpc.publicnode.com")
NFT_CONTRACT = os.getenv("NFT_CONTRACT", "").strip()
SELA_TOKEN_ADDRESS = os.getenv("SELA_TOKEN_ADDRESS", "").strip()
TREASURY_PRIVATE_KEY = os.getenv("TREASURY_PRIVATE_KEY", "").strip()
CHAIN_ID = int(os.getenv("CHAIN_ID", "97"))

ABI_PATH = os.path.join(os.path.dirname(__file__), "abi", "SLHNFT.json")
with open(ABI_PATH, "r", encoding="utf-8") as f:
    SLHNFT_ABI = json.load(f)

w3 = Web3(HTTPProvider(BSC_RPC_URL))

def _pk_to_addr(pk: str) -> str:
    acct = Account.from_key(pk)
    return acct.address

class MintReq(BaseModel):
    to_wallet: str = Field(...)
    token_uri: Optional[str] = None
    tokenURI: Optional[str] = None  # legacy key

class GrantReq(BaseModel):
    to_wallet: str
    amount: Optional[str] = None

@app.get("/healthz")
def healthz():
    return {"ok": True, "network": "BSC Testnet", "contract": NFT_CONTRACT}

@app.post("/v1/chain/mint-demo")
def mint_demo(req: MintReq):
    if not NFT_CONTRACT:
        raise HTTPException(500, "NFT_CONTRACT not set")
    if not TREASURY_PRIVATE_KEY:
        raise HTTPException(500, "No private key configured")

    token_uri = req.token_uri or req.tokenURI
    if token_uri is None:
        raise HTTPException(422, "token_uri is required")

    contract = w3.eth.contract(address=Web3.to_checksum_address(NFT_CONTRACT), abi=SLHNFT_ABI)
    sender = _pk_to_addr(TREASURY_PRIVATE_KEY)

    try:
        tx = contract.functions.mintTo(Web3.to_checksum_address(req.to_wallet), token_uri).build_transaction({
            "from": sender,
            "nonce": w3.eth.get_transaction_count(sender),
            "chainId": CHAIN_ID,
            "gasPrice": w3.eth.gas_price,
        })
    except Exception:
        tx = contract.functions.mintDemo(Web3.to_checksum_address(req.to_wallet)).build_transaction({
            "from": sender,
            "nonce": w3.eth.get_transaction_count(sender),
            "chainId": CHAIN_ID,
            "gasPrice": w3.eth.gas_price,
        })

    signed = w3.eth.account.sign_transaction(tx, private_key=TREASURY_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    return {"tx": tx_hash.hex()}

ERC20_ABI = [
  {"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function","stateMutability":"view"},
  {"constant":True,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function","stateMutability":"view"},
  {"constant":False,"inputs":[{"name":"to","type":"address"},{"name":"value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function","stateMutability":"nonpayable"}
]

@app.post("/v1/chain/grant-sela")
def grant_sela(req: GrantReq):
    if not TREASURY_PRIVATE_KEY:
        raise HTTPException(500, "No private key configured")
    if not SELA_TOKEN_ADDRESS or SELA_TOKEN_ADDRESS == "0x0000000000000000000000000000000000000000":
        raise HTTPException(500, "SELA token address not configured")

    sender = _pk_to_addr(TREASURY_PRIVATE_KEY)
    erc20 = w3.eth.contract(address=Web3.to_checksum_address(SELA_TOKEN_ADDRESS), abi=ERC20_ABI)
    decimals = erc20.functions.decimals().call()
    amt_h = req.amount or os.getenv("SELA_AMOUNT", "0.15984")
    amount_wei = int(float(amt_h) * (10 ** decimals))

    tx = erc20.functions.transfer(Web3.to_checksum_address(req.to_wallet), amount_wei).build_transaction({
        "from": sender,
        "nonce": w3.eth.get_transaction_count(sender),
        "chainId": CHAIN_ID,
        "gasPrice": w3.eth.gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, private_key=TREASURY_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    return {"tx": tx_hash.hex()}
