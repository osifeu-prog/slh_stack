import os
from fastapi import FastAPI
from pydantic import BaseModel
from web3 import Web3, HTTPProvider

RPC_URL = os.getenv("BSC_RPC_URL","https://bsc-testnet-rpc.publicnode.com")
CHAIN_ID = int(os.getenv("CHAIN_ID","97"))
CONTRACT = os.getenv("NFT_CONTRACT","0x8AD1de67648dB44B1b1D0E3475485910CedDe90b")

w3 = Web3(HTTPProvider(RPC_URL))

app = FastAPI(title="SLH API")

class MintReq(BaseModel):
    to_wallet: str
    token_uri: str

class GrantReq(BaseModel):
    to_wallet: str
    amount: str

@app.get("/healthz")
def healthz():
    return {"ok": True, "network": "BSC Testnet", "contract": CONTRACT, "connected": w3.is_connected()}

@app.post("/v1/chain/mint-demo")
def mint_demo(req: MintReq):
    if not os.getenv("TREASURY_PRIVATE_KEY"):
        return {"ok": True, "tx": "0xFAKE_MINT_TX_FOR_TESTS"}
    return {"ok": True, "tx": "0xNOT_IMPLEMENTED_IN_STARTER"}

@app.post("/v1/chain/grant-sela")
def grant_sela(req: GrantReq):
    if not os.getenv("TREASURY_PRIVATE_KEY"):
        return {"ok": True, "tx": "0xFAKE_SELA_TX_FOR_TESTS"}
    return {"ok": True, "tx": "0xNOT_IMPLEMENTED_IN_STARTER"}
