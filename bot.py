import time
from web3 import Web3
import json
from colorama import Fore, Style, init
import os
from dotenv import load_dotenv

init(autoreset=True)
load_dotenv()

RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
YOUR_ADDRESS = os.getenv("YOUR_ADDRESS")

if not all([RPC_URL, PRIVATE_KEY, YOUR_ADDRESS]):
    print("Error: Variabel lingkungan RPC_URL, PRIVATE_KEY, atau YOUR_ADDRESS belum diatur di file .env.")
    exit()

DEX_ROUTER_ABI = []
DEX_ROUTER_ADDRESS = "0x..."

STAKING_CONTRACT_ABI = []
STAKING_CONTRACT_ADDRESS = "0x..."

FAUCET_CONTRACT_ABI = []
FAUCET_CONTRACT_ADDRESS = "0x..."

ERC20_ABI = json.loads("""[{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value":"uint256"}],"name":"approve","outputs":[{"name":"","type":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"_owner":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"}]""")

TOKENS = {
    "KAS": {"address": "0x...", "decimals": 9},
    "wKAS": {"address": "0x...", "decimals": 9},
    "test_ZEAL": {"address": "0x...", "decimals": 18},
    "test_NACHO": {"address": "0x...", "decimals": 18},
    "test_KANGO": {"address": "0x...", "decimals": 18},
    "test_KASPER": {"address": "0x...", "decimals": 18},
    "test_KASPY": {"address": "0x...", "decimals": 18},
    "test_BURT": {"address": "0x...", "decimals": 18},
    "test_KREX": {"address": "0x...", "decimals": 18},
    "test_GHOAD": {"address": "0x...", "decimals": 18},
}

w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print("Error: Gagal terhubung ke RPC Kasplex Testnet. Periksa RPC_URL di file .env Anda.")
    exit()

account = w3.eth.account.from_key(PRIVATE_KEY)
print(f"Bot terhubung dengan alamat: {account.address}")

def get_contract(address, abi):
    return w3.eth.contract(address=w3.to_checksum_address(address), abi=abi)

def send_transaction(tx):
    try:
        gas_price = w3.eth.gas_price
        gas_limit = tx.estimate_gas({'from': account.address, 'value': tx.get('value', 0)})
    except Exception as e:
        print(f"Error memperkirakan gas: {e}. Menggunakan gas limit default.")
        gas_limit = 3_000_000

    transaction = {
        'chainId': w3.eth.chain_id,
        'from': account.address,
        'nonce': w3.eth.get_transaction_count(account.address),
        'gasPrice': gas_price,
        'gas': gas_limit,
        'value': tx.get('value', 0)
    }
    if 'data' in tx: transaction['data'] = tx['data']
    if 'to' in tx: transaction['to'] = tx['to']

    signed_tx = w3.eth.account.sign_transaction(transaction, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print(f"Transaksi dikirim. Hash: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status == 1:
        print(f"Transaksi berhasil dikonfirmasi di blok {receipt.blockNumber}.")
        return True
    else:
        print(f"Transaksi GAGAL: {receipt}.")
        return False

def approve_token(token_symbol, spender_address, amount_float):
    if token_symbol not in TOKENS:
        print(f"Error: Token {token_symbol} tidak ditemukan di daftar TOKENS.")
        return False
    
    token_info = TOKENS[token_symbol]
    token_address = token_info["address"]
    decimals = token_info["decimals"]
    amount_wei = int(amount_float * (10**decimals))

    token_contract = get_contract(token_address, ERC20_ABI)
    current_allowance = token_contract.functions.allowance(account.address, spender_address).call()

    if current_allowance < amount_wei:
        print(f"Menyetujui {spender_address} untuk membelanjakan {amount_float} {token_symbol}...")
        approve_tx = token_contract.functions.approve(spender_address, amount_wei).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address)
        })
        return send_transaction(approve_tx)
    else:
        print(f"Sudah memiliki allowance yang cukup untuk {token_symbol} oleh {spender_address}.")
        return True

def claim_faucet():
    print("Mencoba klaim faucet...")
    faucet_contract = get_contract(FAUCET_CONTRACT_ADDRESS, FAUCET_CONTRACT_ABI)
    try:
        tx = faucet_contract.functions.claimTokens().build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address)
        })
        return send_transaction(tx)
    except Exception as e:
        print(f"Error saat klaim faucet: {e}")
        return False

def swap_tokens(token_in_symbol, token_out_symbol, amount_in_float):
    print(f"Mencoba swap {amount_in_float} {token_in_symbol} ke {token_out_symbol}...")
    if token_in_symbol not in TOKENS or token_out_symbol not in TOKENS:
        print("Error: Simbol token input atau output tidak valid.")
        return False

    token_in_address = TOKENS[token_in_symbol]["address"]
    token_out_address = TOKENS[token_out_symbol]["address"]
    token_in_decimals = TOKENS[token_in_symbol]["decimals"]
    amount_in_wei = int(amount_in_float * (10**token_in_decimals))

    if not approve_token(token_in_symbol, DEX_ROUTER_ADDRESS, amount_in_float):
        print("Gagal menyetujui token untuk swap.")
        return False

    dex_router = get_contract(DEX_ROUTER_ADDRESS, DEX_ROUTER_ABI)
    path = [w3.to_checksum_address(token_in_address), w3.to_checksum_address(token_out_address)]
    deadline = int(time.time()) + 300

    try:
        tx = dex_router.functions.swapExactTokensForTokens(
            amount_in_wei,
            0,
            path,
            account.address,
            deadline
        ).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address)
        })
        return send_transaction(tx)
    except Exception as e:
        print(f"Error saat swap: {e}")
        return False

def add_liquidity(token_a_symbol, token_b_symbol, amount_a_float, amount_b_float):
    print(f"Menambahkan likuiditas {amount_a_float} {token_a_symbol} dan {amount_b_float} {token_b_symbol}...")
    if token_a_symbol not in TOKENS or token_b_symbol not in TOKENS:
        print("Error: Simbol token tidak valid.")
        return False

    token_a_address = TOKENS[token_a_symbol]["address"]
    token_b_address = TOKENS[token_b_symbol]["address"]
    amount_a_wei = int(amount_a_float * (10**TOKENS[token_a_symbol]["decimals"]))
    amount_b_wei = int(amount_b_float * (10**TOKENS[token_b_symbol]["decimals"]))

    if not approve_token(token_a_symbol, DEX_ROUTER_ADDRESS, amount_a_float): return False
    if not approve_token(token_b_symbol, DEX_ROUTER_ADDRESS, amount_b_float): return False

    dex_router = get_contract(DEX_ROUTER_ADDRESS, DEX_ROUTER_ABI)
    deadline = int(time.time()) + 300

    try:
        tx = dex_router.functions.addLiquidity(
            w3.to_checksum_address(token_a_address),
            w3.to_checksum_address(token_b_address),
            amount_a_wei,
            amount_b_wei,
            0,
            0,
            account.address,
            deadline
        ).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address)
        })
        return send_transaction(tx)
    except Exception as e:
        print(f"Error saat menambah likuiditas: {e}")
        return False

def stake_tokens(lp_token_symbol, amount_float):
    print(f"Melakukan staking {amount_float} LP token {lp_token_symbol}...")
    if lp_token_symbol not in TOKENS:
        print(f"Error: LP Token {lp_token_symbol} tidak ditemukan di daftar TOKENS.")
        return False

    lp_token_address = TOKENS[lp_token_symbol]["address"]
    amount_wei = int(amount_float * (10**TOKENS[lp_token_symbol]["decimals"]))

    if not approve_token(lp_token_symbol, STAKING_CONTRACT_ADDRESS, amount_float): return False

    staking_contract = get_contract(STAKING_CONTRACT_ADDRESS, STAKING_CONTRACT_ABI)
    try:
        tx = staking_contract.functions.stake(amount_wei).build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address)
        })
        return send_transaction(tx)
    except Exception as e:
        print(f"Error saat staking: {e}")
        return False

def claim_staking_rewards():
    print("Mencoba klaim rewards staking...")
    staking_contract = get_contract(STAKING_CONTRACT_ADDRESS, STAKING_CONTRACT_ABI)
    try:
        tx = staking_contract.functions.claimRewards().build_transaction({
            'from': account.address,
            'nonce': w3.eth.get_transaction_count(account.address)
        })
        return send_transaction(tx)
    except Exception as e:
        print(f"Error saat klaim rewards staking: {e}")
        return False

def welcome():
    print(Fore.LIGHTGREEN_EX + Style.BRIGHT + "\n" + "═" * 60)
    print(Fore.GREEN + Style.BRIGHT + "    Pharos BOT Tesnet")
    print(Fore.CYAN + Style.BRIGHT + "    ────────────────────────────────")
    print(Fore.YELLOW + Style.BRIGHT + "    Team zonaairdrop")
    print(Fore.CYAN + Style.BRIGHT + "    ────────────────────────────────")
    print(Fore.MAGENTA + Style.BRIGHT + "     Powered by Zonaairdrop")
    print(Fore.LIGHTGREEN_EX + Style.BRIGHT + "═" * 60 + "\n")

def run_auto_bot_loop():
    print("Memulai bot otomatis selama 24 jam.")
    start_time = time.time()
    duration = 24 * 60 * 60

    while True:
        current_time = time.time()
        elapsed_time = current_time - start_time

        if elapsed_time >= duration:
            print("\n24 jam telah berlalu. Me-restart siklus bot...")
            start_time = time.time()

        print(f"\nWaktu berjalan: {int(elapsed_time // 3600)} jam, {int((elapsed_time % 3600) // 60)} menit, {int(elapsed_time % 60)} detik")

        print("\n--- Menjalankan Siklus Otomatis ---")

        print("Aksi: Klaim Faucet...")
        claim_faucet()
        time.sleep(15)

        print("Aksi: Swap test_ZEAL ke test_NACHO...")
        swap_tokens("test_ZEAL", "test_NACHO", 0.001)
        time.sleep(30)

        print("Aksi: Swap test_NACHO kembali ke test_ZEAL...")
        swap_tokens("test_NACHO", "test_ZEAL", 0.0005)
        time.sleep(30)
        
        # add_liquidity("test_ZEAL", "test_NACHO", 0.0001, 0.0001)
        # time.sleep(30)

        # stake_tokens("test_ZEAL-NACHO_LP", 0.00001)
        # time.sleep(30)

        print("Aksi: Klaim Rewards Staking...")
        claim_staking_rewards()
        time.sleep(60)

        print("\nSiklus otomatis selesai. Menunggu siklus berikutnya...")
        time.sleep(5 * 60)

if __name__ == "__main__":
    welcome()
    run_auto_bot_loop()