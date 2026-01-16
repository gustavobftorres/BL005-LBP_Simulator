import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()
ENDPOINT = os.getenv("BALANCER_GQL_ENDPOINT")  # coloque o gateway aqui

def gql(query: str, variables: dict | None = None) -> dict:
    r = requests.post(
        ENDPOINT,
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]

POOL_BY_ADDRESS = """
query PoolByAddress($address: Bytes!) {
  pools(first: 1, where: { address: $address }) {
    id
    address
    poolType
    swapFee
    totalLiquidity
    totalSwapVolume
    tokens {
      address
      symbol
      decimals
      balance
      weight
    }
  }
}
"""

SWAPS_QUERY = """
query Swaps($poolId: String!, $since: Int!) {
  swaps(
    first: 50,
    orderBy: timestamp,
    orderDirection: asc,
    where: { poolId: $poolId, timestamp_gt: $since }
  ) {
    id
    timestamp
    tokenIn
    tokenOut
    tokenAmountIn
    tokenAmountOut
    valueUSD
    tx
  }
}
"""


def get_pool_by_address(pool_address: str) -> dict | None:
    # garante lower-case
    addr = pool_address.lower()
    data = gql(POOL_BY_ADDRESS, {"address": addr})
    pools = data["pools"]
    return pools[0] if pools else None

def stream_swaps(pool_id: str, poll_seconds: int = 10):
    last_ts = int(time.time()) - 3600  # começa olhando última 1 hora (mais dados)
    print(f"🔄 Starting swap stream for pool {pool_id}")
    print(f"📅 Looking for swaps since timestamp: {last_ts}")
    
    while True:
        try:
            data = gql(SWAPS_QUERY, {"poolId": pool_id, "since": last_ts})
            swaps = data["swaps"]
            
            if swaps:
                print(f"✅ Found {len(swaps)} swap(s)")
                for s in swaps:
                    ts = int(s["timestamp"])
                    last_ts = max(last_ts, ts)
                    print(
                        f"[{ts}] {s['tokenIn']} -> {s['tokenOut']} | "
                        f"in={s['tokenAmountIn']} out={s['tokenAmountOut']} "
                        f"usd={s.get('valueUSD', 'N/A')}"
                    )
            else:
                print(f"⏳ No new swaps found (polling every {poll_seconds}s, last_ts={last_ts})")
                
        except Exception as e:
            print(f"❌ Error fetching swaps: {e}")
            
        time.sleep(poll_seconds)



if __name__ == "__main__":
    pool = get_pool_by_address("0x3de27efa2f1aa663ae5d458857e731c129069f29")
    print("Pool info:")
    print(pool)
    print("\n" + "="*60 + "\n")
    
    # Stream swaps - this will run indefinitely
    stream_swaps("0x3de27efa2f1aa663ae5d458857e731c129069f29", poll_seconds=5)



