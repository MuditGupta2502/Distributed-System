# bank_server.py
import grpc
from concurrent import futures
import time
import sys
import json
import os
import sqlite3
import payment_gateway_pb2
import payment_gateway_pb2_grpc

def init_bank_db(bank_name):
    db_file = f"bank_{bank_name}.db"
    conn = sqlite3.connect(db_file, check_same_thread=False)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            client_id TEXT PRIMARY KEY,
            balance REAL,
            account_number TEXT
        )
    ''')
    conn.commit()
    return conn

def load_accounts_from_db(conn):
    cur = conn.cursor()
    cur.execute("SELECT client_id, balance, account_number FROM accounts")
    accounts = {}
    for client_id, balance, account_number in cur.fetchall():
        accounts[client_id] = {"balance": balance, "account_number": account_number}
    return accounts

def save_accounts_to_db(conn, accounts):
    cur = conn.cursor()
    for client_id, data in accounts.items():
        cur.execute(
            "INSERT OR REPLACE INTO accounts (client_id, balance, account_number) VALUES (?, ?, ?)",
            (client_id, data["balance"], data["account_number"])
        )
    conn.commit()

class BankServiceServicer(payment_gateway_pb2_grpc.BankServiceServicer):
    def __init__(self, bank_name):
        self.bank_name = bank_name
        self.prepared_transactions = {}
        # Initialize or load account balances.
        self.db_conn = init_bank_db(bank_name)
        # Try to load from DB first.
        accounts = load_accounts_from_db(self.db_conn)
        if accounts:
            self.accounts = accounts
            print(f"[{self.bank_name}] Loaded {len(self.accounts)} accounts from database.")
        else:
            # If DB is empty, load from users.json and persist.
            self.accounts = {}
            if os.path.exists("users.json"):
                with open("users.json", "r") as f:
                    data = json.load(f)
                    for user in data.get("clients", []):
                        if user["bank"] == self.bank_name:
                            self.accounts[user["client_id"]] = {
                                "balance": user["balance"],
                                "account_number": user["account_number"]
                            }
                save_accounts_to_db(self.db_conn, self.accounts)
                print(f"[{self.bank_name}] Loaded {len(self.accounts)} accounts from users.json and saved to database.")
            else:
                print(f"[{self.bank_name}] users.json not found. Starting with empty accounts.")

    def Ping(self, request, context):
        return payment_gateway_pb2.PingResponse(message="pong")

    def GetBalance(self, request, context):
        client_id = request.client_id
        if client_id not in self.accounts:
            return payment_gateway_pb2.BalanceResponse(success=False, message="Account not found", balance=0.0)
        balance = self.accounts[client_id]["balance"]
        return payment_gateway_pb2.BalanceResponse(success=True, message="Balance retrieved", balance=balance)

    def PrepareTransaction(self, request, context):
        client_id = request.account_id
        if request.is_debit:
            ''' # 2PhaseCommit Testcase
            if request.transaction_id == 00000000000000:
               import time
               time.sleep(7)'
            '''
            if client_id not in self.accounts:
                return payment_gateway_pb2.TransactionResponse(ready=False, message="Account not found")
            if self.accounts[client_id]["balance"] < request.amount:
                return payment_gateway_pb2.TransactionResponse(ready=False, message="INSUFFICIENT_FUNDS")
            # Hold the funds (for simulation, just record the amount)
            self.prepared_transactions[request.transaction_id] = request.amount
            return payment_gateway_pb2.TransactionResponse(ready=True, message="Debit prepared")
        else:
            # For credit, no check is needed.
            return payment_gateway_pb2.TransactionResponse(ready=True, message="Credit prepared")

    def CommitTransaction(self, request, context):
        client_id = request.account_id
        if request.is_debit:
            if request.transaction_id not in self.prepared_transactions:
                return payment_gateway_pb2.TransactionResponse(ready=False, message="Transaction not prepared")
            amount = self.prepared_transactions.pop(request.transaction_id)
            self.accounts[client_id]["balance"] -= amount
            save_accounts_to_db(self.db_conn, self.accounts)
            return payment_gateway_pb2.TransactionResponse(ready=True, message="Debit committed")
        else:
            # For credit, add the funds.
            if client_id not in self.accounts:
                self.accounts[client_id] = {"balance": 0.0, "account_number": ""}
            self.accounts[client_id]["balance"] += request.amount
            save_accounts_to_db(self.db_conn, self.accounts)
            return payment_gateway_pb2.TransactionResponse(ready=True, message="Credit committed")

    def AbortTransaction(self, request, context):
        if request.transaction_id in self.prepared_transactions:
            del self.prepared_transactions[request.transaction_id]
        return payment_gateway_pb2.TransactionResponse(ready=True, message="Transaction aborted")

def serve():
    if len(sys.argv) < 2:
        print("Usage: python bank_server.py <BankName>")
        sys.exit(1)
    bank_name = sys.argv[1]
    ports = {
        "HDFC": 50051,
        "ICICI": 50052,
        "Axis": 50053,
        "Canara": 50054,
        "Kotak": 50055,
        "BankOfIndia": 50056
    }
    port = ports.get(bank_name, 50057)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    payment_gateway_pb2_grpc.add_BankServiceServicer_to_server(BankServiceServicer(bank_name), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    print(f"[{bank_name}] Bank server started on port {port}")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve()
