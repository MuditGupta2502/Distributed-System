# client.py
import argparse
import grpc
import time
import uuid
import threading
import payment_gateway_pb2
import payment_gateway_pb2_grpc

offline_queue = []
gateway_address = "localhost:50050"

# Global registration data and current auth token.
REGISTRATION_DATA = {}
CURRENT_AUTH_TOKEN = None

# client.py (snippet showing mutual TLS secure channel creation)
def get_secure_channel(address):
    with open('certs/ca.crt', 'rb') as f:
        trusted_certs = f.read()
    with open('certs/client.key', 'rb') as f:
        client_key = f.read()
    with open('certs/client.crt', 'rb') as f:
        client_cert = f.read()
    credentials = grpc.ssl_channel_credentials(
        root_certificates=trusted_certs,
        private_key=client_key,
        certificate_chain=client_cert
    )
    return grpc.secure_channel(address, credentials)


def register_client(client_id, username, password, bank):
    global CURRENT_AUTH_TOKEN, REGISTRATION_DATA
    REGISTRATION_DATA = {
        "client_id": client_id,
        "username": username,
        "password": password,
        "bank": bank
    }
    try:
        channel = get_secure_channel(gateway_address)
        stub = payment_gateway_pb2_grpc.PaymentGatewayStub(channel)
        client_info = payment_gateway_pb2.ClientInfo(
            client_id=client_id,
            username=username,
            password=password,
            bank=bank
        )
        response = stub.RegisterClient(client_info)
        print(f"[Client {client_id}] Registration response: {response.message}")
        if response.success:
            CURRENT_AUTH_TOKEN = f"token-{client_id}"
        return response
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            print(f"[Client {client_id}] Payment gateway is down. Please try again later.")
        else:
            print(f"[Client {client_id}] RPC error: {e.code()} - {e.details()}")
        return None

def process_payment(client_id, from_bank, recipient_account, amount, auth_token, transaction_id=None):
    if transaction_id is None:
        transaction_id = str(uuid.uuid4())
    payment_request = payment_gateway_pb2.PaymentRequest(
        transaction_id=transaction_id,
        client_id=client_id,
        from_bank=from_bank,
        recipient_account_number=recipient_account,
        amount=amount,
        auth_token=auth_token
    )
    try:
        channel = get_secure_channel(gateway_address)
        stub = payment_gateway_pb2_grpc.PaymentGatewayStub(channel)
        metadata = [("client-id", client_id), ("auth-token", auth_token)]
        response = stub.ProcessPayment(payment_request, metadata=metadata)
        print(f"[Client {client_id}] Transfer response: {response.message}")
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            print(f"[Client {client_id}] Payment gateway is down ({e.code()}), queuing transaction for retry.")
            offline_queue.append(payment_request)
        elif e.code() == grpc.StatusCode.UNAUTHENTICATED:
            print(f"[Client {client_id}] UNAUTHENTICATED error: {e.details()}. Attempting re-registration.")
            reg_response = register_client(client_id, REGISTRATION_DATA["username"], REGISTRATION_DATA["password"], REGISTRATION_DATA["bank"])
            if reg_response and reg_response.success:
                auth_token = CURRENT_AUTH_TOKEN
                try:
                    channel = get_secure_channel(gateway_address)
                    stub = payment_gateway_pb2_grpc.PaymentGatewayStub(channel)
                    metadata = [("client-id", client_id), ("auth-token", auth_token)]
                    response = stub.ProcessPayment(payment_request, metadata=metadata)
                    print(f"[Client {client_id}] Transfer response after re-registration: {response.message}")
                except grpc.RpcError as e2:
                    print(f"[Client {client_id}] RPC error after re-registration: {e2}. Queuing transaction for retry.")
                    offline_queue.append(payment_request)
            else:
                print(f"[Client {client_id}] Re-registration failed. Queuing transaction for retry.")
                offline_queue.append(payment_request)
        else:
            print(f"[Client {client_id}] RPC error: {e.code()} - {e.details()}. Not re-queuing transaction.")

def view_balance(client_id, auth_token):
    try:
        channel = get_secure_channel(gateway_address)
        stub = payment_gateway_pb2_grpc.PaymentGatewayStub(channel)
        metadata = [("client-id", client_id), ("auth-token", auth_token)]
        balance_request = payment_gateway_pb2.BalanceRequest(client_id=client_id, auth_token=auth_token)
        response = stub.ViewBalance(balance_request, metadata=metadata)
        if not response.success:
            # Print the error message from the server (e.g., "Bank server for HDFC is down")
            print(f"[Client {client_id}] {response.message}")
        else:
            print(f"[Client {client_id}] Balance: {response.balance}")
        return response.balance if response.success else None
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            print(f"[Client {client_id}] Payment gateway is down while viewing balance. Please try again later.")
        elif e.code() == grpc.StatusCode.UNAUTHENTICATED:
            print(f"[Client {client_id}] UNAUTHENTICATED error while viewing balance: {e.details()}. Attempting re-registration.")
            reg_response = register_client(client_id, REGISTRATION_DATA["username"], REGISTRATION_DATA["password"], REGISTRATION_DATA["bank"])
            if reg_response and reg_response.success:
                return view_balance(client_id, CURRENT_AUTH_TOKEN)
            else:
                print(f"[Client {client_id}] Re-registration failed while viewing balance.")
        else:
            print(f"[Client {client_id}] RPC error while viewing balance: {e.code()} - {e.details()}")
        return None

def retry_offline_payments():
    global CURRENT_AUTH_TOKEN
    while True:
        if offline_queue:
            print("[Client] Retrying offline transactions...")
            pending = offline_queue.copy()
            offline_queue.clear()
            for payment_request in pending:
                try:
                    channel = get_secure_channel(gateway_address)
                    stub = payment_gateway_pb2_grpc.PaymentGatewayStub(channel)
                    metadata = [("client-id", payment_request.client_id), ("auth-token", CURRENT_AUTH_TOKEN)]
                    response = stub.ProcessPayment(payment_request, metadata=metadata)
                    print(f"[Client {payment_request.client_id}] Offline Transfer response: {response.message}")
                except grpc.RpcError as e:
                    if e.code() == grpc.StatusCode.UNAVAILABLE:
                        print(f"[Client {payment_request.client_id}] Payment gateway still down during retry ({e.code()}), re-queuing transaction.")
                        offline_queue.append(payment_request)
                    elif e.code() == grpc.StatusCode.UNAUTHENTICATED:
                        print(f"[Client {payment_request.client_id}] UNAUTHENTICATED during retry: {e.details()}. Attempting re-registration.")
                        reg_response = register_client(payment_request.client_id, REGISTRATION_DATA["username"], REGISTRATION_DATA["password"], REGISTRATION_DATA["bank"])
                        if reg_response and reg_response.success:
                            metadata = [("client-id", payment_request.client_id), ("auth-token", CURRENT_AUTH_TOKEN)]
                            try:
                                response = stub.ProcessPayment(payment_request, metadata=metadata)
                                print(f"[Client {payment_request.client_id}] Offline Transfer response after re-registration: {response.message}")
                            except grpc.RpcError as e2:
                                print(f"[Client {payment_request.client_id}] RPC error after re-registration during retry: {e2}. Re-queuing transaction.")
                                offline_queue.append(payment_request)
                        else:
                            print(f"[Client {payment_request.client_id}] Re-registration failed during retry. Not re-queuing transaction.")
                    else:
                        print(f"[Client {payment_request.client_id}] RPC error during retry: {e.code()} - {e.details()}. Not re-queuing transaction.")
        time.sleep(5)

def interactive_mode(client_id, bank, auth_token):
    print("Enter command (view, transfer <amount> <recipient_account_number>, exit):")
    while True:
        cmd = input(">> ").strip().split()
        if not cmd:
            continue
        if cmd[0].lower() == "view":
            view_balance(client_id, CURRENT_AUTH_TOKEN)
        elif cmd[0].lower() == "transfer":
            if len(cmd) != 3:
                print("Usage: transfer <amount> <recipient_account_number>")
                continue
            try:
                amount = float(cmd[1])
            except ValueError:
                print("Invalid amount")
                continue
            recipient_account = cmd[2]
            if len(recipient_account) != 14 or not recipient_account.isdigit():
                print("Recipient account number must be 14 digits")
                continue
            process_payment(client_id, from_bank=bank, recipient_account=recipient_account, amount=amount, auth_token=CURRENT_AUTH_TOKEN)
        elif cmd[0].lower() == "exit":
            print("Exiting interactive mode.")
            break
        else:
            print("Unknown command. Use view, transfer <amount> <recipient_account_number>, or exit.")

def main():
    parser = argparse.ArgumentParser(description="Payment Gateway Client")
    parser.add_argument("--client_id", required=True, help="Client ID (e.g., client1)")
    parser.add_argument("--username", required=True, help="Username (e.g., user1)")
    parser.add_argument("--password", required=True, help="Password (e.g., pass1)")
    parser.add_argument("--bank", required=True, help="Client's bank name (e.g., HDFC)")
    args = parser.parse_args()

    threading.Thread(target=retry_offline_payments, daemon=True).start()

    reg_response = register_client(args.client_id, args.username, args.password, args.bank)
    if not reg_response or not reg_response.success:
        print("Registration failed. Exiting.")
        exit(1)
    interactive_mode(args.client_id, args.bank, CURRENT_AUTH_TOKEN)

if __name__ == '__main__':
    main()
