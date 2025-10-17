
from web3 import Web3, HTTPProvider
import json, sys, os

RPC  = os.getenv("BSC_RPC_URL","https://bsc-testnet-rpc.publicnode.com")
ADDR = os.getenv("NFT_CONTRACT","0x8AD1de67648dB44B1b1D0E3475485910CedDe90b")

ABI_PATH = os.path.join(os.path.dirname(__file__), "..", "abi", "SLHNFT.json")
token_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1

w3 = Web3(HTTPProvider(RPC))
with open(ABI_PATH, "r", encoding="utf-8") as f:
    abi = json.load(f)

c = w3.eth.contract(address=Web3.to_checksum_address(ADDR), abi=abi)

owner = c.functions.ownerOf(token_id).call()
uri   = c.functions.tokenURI(token_id).call()

print(f"ownerOf({token_id}): {owner}")
print(f"tokenURI({token_id}): {uri}")
