# payment_gateway_server.py
import grpc
from concurrent import futures
import time
import json
import os
import sqlite3
import logging

import payment_gateway_pb2
import payment_gateway_pb2_grpc

# Configure logging to file.
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "server.log")),
        logging.StreamHandler()  # Optionally, also log to console.
    ]
)
logger = logging.getLogger(__name__)

# Global in-memory state for registration and idempotency (not for balances)
stored_users = {}            # Loaded from users.json; each user includes client_id, username, password, bank, role, account_number
authenticated_clients = {}   # Mapping: client_id -> auth_token
processed_transactions = {}  # Mapping: transaction_id -> status ("committed" means processed)

# -------------------------------
# Database Functions for Fault Tolerance
# -------------------------------
def init_db(db_file="gateway_state.db"):
    conn = sqlite3.connect(db_file, check_same_thread=False)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id TEXT PRIMARY KEY,
            status TEXT
        )
    ''')
    conn.commit()
    return conn

def load_state_from_db(conn):
    cur = conn.cursor()
    cur.execute("SELECT transaction_id, status FROM transactions")
    for txn_id, status in cur.fetchall():
        processed_transactions[txn_id] = status

def update_transaction_in_db(conn, transaction_id, status):
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO transactions (transaction_id, status) VALUES (?, ?)", (transaction_id, status))
    conn.commit()

def load_users(json_file="users.json"):
    global stored_users
    if os.path.exists(json_file):
        with open(json_file, "r") as f:
            data = json.load(f)
            for user in data.get("clients", []):
                stored_users[user["client_id"]] = user
            logger.info(f"Loaded {len(stored_users)} users from {json_file}")
    else:
        logger.error(f"Users file {json_file} not found.")

# -------------------------------
# Bank Server Mapping and Connectivity Check
# -------------------------------
bank_addresses = {
    "HDFC": "localhost:50051",
    "ICICI": "localhost:50052",
    "Axis": "localhost:50053",
    "Canara": "localhost:50054",
    "Kotak": "localhost:50055",
    "BankOfIndia": "localhost:50056"
}
TWO_PHASE_TIMEOUT = 5.0
PING_TIMEOUT = 2.0

def check_bank_server(bank_name):
    if bank_name not in bank_addresses:
        return False
    channel = grpc.insecure_channel(bank_addresses[bank_name])
    stub = payment_gateway_pb2_grpc.BankServiceStub(channel)
    try:
        response = stub.Ping(payment_gateway_pb2.Empty(), timeout=PING_TIMEOUT)
        return response.message.lower() == "pong"
    except grpc.RpcError as e:
        logger.error(f"Ping to {bank_name} failed: {e}")
        return False

# -------------------------------
# gRPC Interceptors
# -------------------------------
class LoggingInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method
        metadata = handler_call_details.invocation_metadata or []
        client_id = None
        for key, value in metadata:
            if key == "client-id":
                client_id = value
                break
        logger.info(f"Incoming request: Method={method}, ClientID={client_id}")
        handler = continuation(handler_call_details)
        if handler is None:
            logger.error(f"No handler for {method}")
            return None
        if handler.unary_unary:
            original_unary_unary = handler.unary_unary
            def new_unary_unary(request, context):
                amount = getattr(request, "amount", None)
                logger.info(f"Request for {method} from client {client_id}: {request} (Amount: {amount})")
                try:
                    response = original_unary_unary(request, context)
                    logger.info(f"Response for {method} to client {client_id}: {response}")
                    return response
                except Exception as e:
                    logger.error(f"Error in {method} for client {client_id}: {e}")
                    raise e
            return grpc.unary_unary_rpc_method_handler(
                new_unary_unary,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer
            )
        return handler

class AuthInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method
        if "RegisterClient" in method:
            return continuation(handler_call_details)
        metadata = {}
        if handler_call_details.invocation_metadata:
            for key, value in handler_call_details.invocation_metadata:
                metadata[key] = value
        client_id = metadata.get("client-id")
        auth_token = metadata.get("auth-token")
        if not client_id or not auth_token:
            def abort_handler(request, context):
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing auth metadata")
            return grpc.unary_unary_rpc_method_handler(abort_handler)
        if client_id not in authenticated_clients or authenticated_clients[client_id] != auth_token:
            def abort_handler(request, context):
                context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid auth token")
            return grpc.unary_unary_rpc_method_handler(abort_handler)
        user = stored_users.get(client_id, {})
        if user.get("role", "client") != "client":
            def abort_handler(request, context):
                context.abort(grpc.StatusCode.PERMISSION_DENIED, "Permission denied")
            return grpc.unary_unary_rpc_method_handler(abort_handler)
        return continuation(handler_call_details)

# -------------------------------
# PaymentGateway Service Implementation with 2PC and Persistence
# -------------------------------
class PaymentGatewayServicer(payment_gateway_pb2_grpc.PaymentGatewayServicer):
    def RegisterClient(self, request, context):
        client_id = request.client_id
        if client_id not in stored_users:
            return payment_gateway_pb2.RegisterResponse(success=False, message="Client not found.")
        user_info = stored_users[client_id]
        client_bank = user_info["bank"]
        if not check_bank_server(client_bank):
            return payment_gateway_pb2.RegisterResponse(success=False,
                                                         message=f"Bank server for {client_bank} is not available.")
        if request.username != user_info["username"] or request.password != user_info["password"]:
            return payment_gateway_pb2.RegisterResponse(success=False, message="Invalid username or password.")
        if client_id in authenticated_clients:
            token = authenticated_clients[client_id]
            return payment_gateway_pb2.RegisterResponse(success=True, message=f"Already registered. Auth token: {token}")
        token = f"token-{client_id}"
        authenticated_clients[client_id] = token
        logger.info(f"Client {client_id} authenticated successfully.")
        return payment_gateway_pb2.RegisterResponse(success=True, message=f"Registered successfully. Auth token: {token}")

    def ProcessPayment(self, request, context):
        client_id = request.client_id
        sender = stored_users.get(client_id)
        amount = request.amount
        transaction_id = request.transaction_id
        recipient_account = request.recipient_account_number

        if transaction_id in processed_transactions and processed_transactions[transaction_id] == "committed":
            return payment_gateway_pb2.PaymentResponse(success=True, message="Transaction already processed (idempotent).")

        if not check_bank_server(sender["bank"]):
            return payment_gateway_pb2.PaymentResponse(success=False,
                                                       message=f"Sender bank server ({sender['bank']}) is not available.")

        recipient = None
        recipient_client_id = None
        for cid, user in stored_users.items():
            if user.get("account_number") == recipient_account:
                recipient = user
                recipient_client_id = cid
                break
        if recipient is None:
            return payment_gateway_pb2.PaymentResponse(success=False, message="Recipient account not found.")

        if not check_bank_server(recipient["bank"]):
            return payment_gateway_pb2.PaymentResponse(success=False,
                                                       message=f"Recipient bank server ({recipient['bank']}) is not available.")

        try:
            # Create separate transaction requests: one for debit and one for credit.
            debit_request = payment_gateway_pb2.TransactionRequest(
                transaction_id=transaction_id,
                amount=amount,
                account_id=client_id,
                is_debit=True
            )
            credit_request = payment_gateway_pb2.TransactionRequest(
                transaction_id=transaction_id,
                amount=amount,
                account_id=recipient_client_id,
                is_debit=False
            )
            with grpc.insecure_channel(bank_addresses[sender["bank"]]) as channel_from, \
                 grpc.insecure_channel(bank_addresses[recipient["bank"]]) as channel_to:
                sender_stub = payment_gateway_pb2_grpc.BankServiceStub(channel_from)
                recipient_stub = payment_gateway_pb2_grpc.BankServiceStub(channel_to)
                # Phase 1: Prepare Phase
                prep_sender = sender_stub.PrepareTransaction(debit_request, timeout=TWO_PHASE_TIMEOUT)
                prep_recipient = recipient_stub.PrepareTransaction(credit_request, timeout=TWO_PHASE_TIMEOUT)
                if not (prep_sender.ready and prep_recipient.ready):
                    logger.error(f"Prepare phase failed for transaction {transaction_id}: {prep_sender.message}, {prep_recipient.message}")
                    try:
                        sender_stub.AbortTransaction(debit_request, timeout=TWO_PHASE_TIMEOUT)
                    except Exception:
                        pass
                    try:
                        recipient_stub.AbortTransaction(credit_request, timeout=TWO_PHASE_TIMEOUT)
                    except Exception:
                        pass
                    processed_transactions[transaction_id] = "aborted"
                    update_transaction_in_db(db_conn, transaction_id, "aborted")
                    return payment_gateway_pb2.PaymentResponse(success=False,
                                                               message="Transaction aborted in prepare phase.")
                # Phase 2: Commit Phase
                commit_sender = sender_stub.CommitTransaction(debit_request, timeout=TWO_PHASE_TIMEOUT)
                commit_recipient = recipient_stub.CommitTransaction(credit_request, timeout=TWO_PHASE_TIMEOUT)
                if commit_sender.ready and commit_recipient.ready:
                    processed_transactions[transaction_id] = "committed"
                    update_transaction_in_db(db_conn, transaction_id, "committed")
                    logger.info(f"Transaction {transaction_id} committed successfully.")
                    return payment_gateway_pb2.PaymentResponse(success=True,
                                                               message="Transaction committed successfully.")
                else:
                    logger.error(f"Commit phase failed for transaction {transaction_id}")
                    try:
                        sender_stub.AbortTransaction(debit_request, timeout=TWO_PHASE_TIMEOUT)
                    except Exception:
                        pass
                    try:
                        recipient_stub.AbortTransaction(credit_request, timeout=TWO_PHASE_TIMEOUT)
                    except Exception:
                        pass
                    processed_transactions[transaction_id] = "failed"
                    update_transaction_in_db(db_conn, transaction_id, "failed")
                    return payment_gateway_pb2.PaymentResponse(success=False,
                                                               message="Transaction commit failed.")
        except grpc.RpcError as e:
            processed_transactions[transaction_id] = "failed"
            update_transaction_in_db(db_conn, transaction_id, "failed")
            return payment_gateway_pb2.PaymentResponse(success=False,
                                                       message=f"RPC error during transaction processing: {e}")

    def ViewBalance(self, request, context):
        client_id = request.client_id
        user = stored_users.get(client_id)
        if user is None:
            return payment_gateway_pb2.BalanceResponse(success=False, message="User not found", balance=0.0)
        bank_name = user["bank"]
        try:
            channel = grpc.insecure_channel(bank_addresses[bank_name])
            stub = payment_gateway_pb2_grpc.BankServiceStub(channel)
            response = stub.GetBalance(request, timeout=PING_TIMEOUT)
            return response
        except grpc.RpcError as e:
            error_msg = f"Failed to get balance from bank server for {bank_name}: {e}. A balance value of -1.0 indicates that no valid balance could be retrieved."
            logger.error(error_msg)
            print(error_msg)
            # Return a response with balance set to 0.0 instead of -1.0.
            return payment_gateway_pb2.BalanceResponse(success=False, message=f"Bank server for {bank_name} is down.", balance=0.0)



# -------------------------------
# Main Server Setup
# -------------------------------
db_conn = None

def serve():
    global db_conn
    load_users("users.json")
    db_conn = init_db()
    load_state_from_db(db_conn)
    interceptors = [LoggingInterceptor(), AuthInterceptor()]
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), interceptors=interceptors)
    payment_gateway_pb2_grpc.add_PaymentGatewayServicer_to_server(PaymentGatewayServicer(), server)
    
    with open('certs/server.key', 'rb') as f:
        private_key = f.read()
    with open('certs/server.crt', 'rb') as f:
        certificate = f.read()
    with open('certs/ca.crt', 'rb') as f:
        client_ca_cert = f.read()
    server_credentials = grpc.ssl_server_credentials([(private_key, certificate)],root_certificates=client_ca_cert,
    require_client_auth=True)

    server.add_secure_port('[::]:50050', server_credentials)
    server.start()
    logger.info("PaymentGateway Secure server started on port 50050")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    serve()
