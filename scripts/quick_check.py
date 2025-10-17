from web3 import Web3, HTTPProvider
import json, sys

RPC  = "https://bsc-testnet-rpc.publicnode.com"
ADDR = "0x8AD1de67648dB44B1b1D0E3475485910CedDe90b"  # checksum
ABI  = "abi/SLHNFT.json"

if __name__ == "__main__":
    w3 = Web3(HTTPProvider(RPC))
    with open(ABI, "r", encoding="utf-8-sig") as f:
        abi = json.load(f)
    c = w3.eth.contract(address=ADDR, abi=abi)
    tid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print("name():", c.functions.name().call())
    print("symbol():", c.functions.symbol().call())
    print(f"ownerOf({tid}):", c.functions.ownerOf(tid).call())
    print(f"tokenURI({tid}):", c.functions.tokenURI(tid).call())
