Below are the complete terminal commands (using OpenSSL) from scratch to generate a Certificate Authority (CA), a server certificate (server.crt and server.key), and a client certificate (client.crt and client.key). These certificates will enable mutual TLS.

# 1. Generate a CA Key and Self-Signed Certificate

First, generate a private key for the CA:
openssl genrsa -out ca.key 2048

Now create a self‑signed CA certificate (you’ll be prompted for details such as Country, Organization, Common Name, etc. For Common Name do NOT put localhost, put a dummy name):
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt


# 2. Generate the Server Certificate

Generate the server’s private key:
openssl genrsa -out server.key 2048

Create a Certificate Signing Request (CSR) for the server (when prompted for the Common Name, enter your server's hostname; for local testing you can use “localhost”):
openssl req -new -key server.key -out server.csr

Sign the server CSR using your CA certificate to generate the server certificate:
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365 -sha256

# 3. Generate the Client Certificate

Generate the client’s private key:
openssl genrsa -out client.key 2048

Create a CSR for the client (for the Common Name, you might use an identifier like “client1” or similar):
openssl req -new -key client.key -out client.csr

Sign the client CSR using your CA certificate:
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 3

-------------------------------------------------------------------------------------------------

#  Directory Structure :

Ensure your project directory is structured as follows:


project_root/
├── certs/
│   ├── ca.crt
│   ├── server.crt
│   ├── server.key
│   ├── client.crt
│   └── client.key
├── logs/
│   └── server.log
├── payment_gateway.proto
├── payment_gateway_server.py   # Configured for mutual TLS
├── bank_server.py              # Configured for mutual TLS
├── client.py                   # Configured for mutual TLS
└── users.json                  # Dummy user data

----------------------------------------------------------------------------------------------------

# 0. Generate protofiles

python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. payment_gateway.proto

On running the above command in linux terminal, two files are genrated :
payment_gateway_pb2_grpc.py   and   payment_gateway_pb2.py


# 1. Start the Payment Gateway Server :

Open a terminal, navigate to your project directory, and run:
python3 payment_gateway_server.py

The server will load its certificates (server.crt, server.key, ca.crt) and start securely on port 50050. You should see a log message like:
[PaymentGateway] Secure server started on port 50050


# 2. Start the Bank Servers :

For each bank you want to simulate, open a separate terminal window (or tab) and run the bank server. For example, to start the HDFC bank server:
python3 bank_server.py HDFC

Similarly, start any additional bank servers as needed (e.g., ICICI, Axis, etc.). The bank servers use mutual TLS in a similar manner (though typically they’re configured to use one-way TLS in our simulation, they still verify via the CA certificate).

# 3. Run the Client : 

Open another terminal and run the client. For example, to run a client for client1 associated with HDFC:
python3 client.py --client_id client1 --username user1 --password pass1 --bank HDFC

The client will load its own certificates (client.crt and client.key) along with ca.crt, create a secure channel to the Payment Gateway, and then authenticate. You'll see messages indicating successful registration and subsequent operations (like viewing balance or making transfers).

# 4. Interact with the Client :

Once the client is running in interactive mode, you can type commands like:

view – to view your current balance.
transfer 500 23456789012345 – to transfer 500 to a recipient whose 14‑digit account number is provided.
exit – to exit interactive mode.