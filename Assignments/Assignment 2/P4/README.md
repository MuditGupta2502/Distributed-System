# Distributed Byzantine Generals Solution

This assignment implements a distributed solution for the Byzantine Generals Problem using Lamport’s OT algorithm. The solution uses gRPC in Python to simulate independent server processes (one per general), which communicate with each other to reach consensus in the presence of faulty (traitorous) nodes.
----------------------------------------------------------------------------------------------------

# 1. Compile the Proto File: In the repository root, run:
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. byzantine.proto

This will generate the files:

byzantine_pb2.py
byzantine_pb2_grpc.py

===================================================================================================
# Running the Distributed Solution

# Step 1: Spawn the Distributed Servers
Run the scale_server.py script to launch all server processes. For example, to spawn 10 generals with generals 3, 4, and 7 marked as traitors and with a base port of 50051:


python scale_server.py --num_generals 10 --traitors 3,4,7 --base_port 50051

What is generated?
10 server processes, each listening on ports 50051 to 50060.
Each server (general) creates or resets its intermediate log file named general_<id>_intermediate.log.

# Step 2: Run the Distributed Client
Once the servers are running, trigger the OT algorithm and view the consensus by running:

python distributed_client.py --order ATTACK --t 3 --num_generals 10 --base_port 50051 --generals l,l,l,t,t,l,l,t,l,l

Client Actions:
Resets the log files on all generals via the ResetLog RPC.
Contacts the commander (general 0) to start the algorithm with order "ATTACK" and recursion depth (t) of 3.
Collects vote tallies from all generals.
Computes and prints the final consensus among the loyal generals.
Expected Output: The client terminal will display vote tallies from each general, for example:

Vote tallies from generals:
General 0:
  ATTACK: 314
  RETREAT: 262
General 1:
  ATTACK: 412
  RETREAT: 164
General 2:
  ATTACK: 314
  RETREAT: 262
General 3:
  ATTACK: 412
  RETREAT: 164
General 4:
  ATTACK: 314
  RETREAT: 262
General 5:
  ATTACK: 412
  RETREAT: 164
General 6:
  ATTACK: 314
  RETREAT: 262
General 7:
  ATTACK: 412
  RETREAT: 164
General 8:
  ATTACK: 314
  RETREAT: 262
General 9:
  ATTACK: 412
  RETREAT: 164

Final consensus reached: ATTACK
Intermediate Log Files
Each general’s server logs detailed execution information in its log file (e.g., general_9_intermediate.log). These logs include:

Receipt of orders with a mapped round number.
Details when traitors flip the order.
Messages showing when orders are forwarded between servers.
The logs help trace the entire execution process of the recursive OT algorithm and verify that consensus is achieved despite the presence of traitors.
===================================================================================================

## Components

- **byzantine.proto**  
  Defines the gRPC service, messages, and RPC methods:
  - `RunAlgorithm`: Initiates the OT algorithm (only allowed from the commander, general 0).
  - `SendOrder`: For inter-server order propagation.
  - `GetDecision`: Returns the vote tally from a general.
  - `ResetLog`: Clears the general's intermediate log file.

- **distributed_server.py**  
  Implements the logic for an individual general. Each server:
  - Runs the recursive OT algorithm.
  - Logs intermediate steps (message reception, order flipping, etc.) to a dedicated log file (`general_<id>_intermediate.log`).
  - Communicates with peers via gRPC.

- **scale_server.py**  
  Automates the spawning of multiple server processes:
  - Accepts command-line arguments for the total number of generals, traitor indices, and base port.
  - Assigns a unique port to each general (e.g., from 50051 to 50060).
  - Passes the full list of peer addresses to every server.

- **distributed_client.py**  
  Acts as the client to:
  - Reset the log files on all servers before a new run.
  - Trigger the OM algorithm by contacting the commander (general 0).
  - Collect vote tallies from all generals.
  - Compute and display the final consensus.

## Requirements

- Python 3.x
- gRPC packages:
  pip install grpcio grpcio-tools
