Below is an example sequence of terminal commands (for Linux/WSL) to run the entire system—from starting Consul to running the LB server (with each policy), spawning backend servers, and finally running the client scale test (now renamed as scale_clients.py). Adjust the number of servers and clients as needed. 
Note: You’ll need to have a Consul agent running (by default on localhost:8500) and install the Python Consul library (e.g. via “pip install python-consul”) for these modifications to work.

1. # Start Consul in Development Mode
Open a terminal (or WSL session) and run: consul agent -dev
This starts Consul on localhost:8500 and registers services in development mode.

2. # Generate gRPC code:
Run the following command (assuming you have protoc and the gRPC Python plugin installed):
python3 -m grpc_tools.protoc --python_out=. --grpc_python_out=. --proto_path=. load_balancer.proto

3. # Run the LB Server with a Specific Load Balancing Policy
Open a new terminal for the LB server. For each policy, run the LB server with the appropriate --policy argument. For example:

For Pick First:
python3 lb_server.py --port 50051 --policy pick_first --consul_host localhost --consul_port 8500

For Round Robin:
python3 lb_server.py --port 50051 --policy round_robin --consul_host localhost --consul_port 8500

For Least Load:
python3 lb_server.py --port 50051 --policy least_load --consul_host localhost --consul_port 8500

You will test one policy at a time. Stop the LB server (Ctrl+C) before switching policies.

4. # Spawn Multiple Backend Servers Using scale_servers.py
Open another terminal and run the script to spawn, for example, 10 backend servers starting at port 50052:
python3 scale_servers.py --num_servers 10 --starting_port 50052 --consul_host localhost --consul_port 8500 --report_interval 5

This will launch 10 backend server processes, each registering with the LB server and reporting load every 5 seconds.

5. # Run the Client Scale Test Using scale_clients.py
Open a new terminal and run the scale test with 100 concurrent clients:
python3 scale_clients.py --num_clients 100 --consul_host localhost --consul_port 8500

This script will simulate 100 clients concurrently making compute requests. It will print out the average, minimum, and maximum response times, throughput (requests per second), and the backend usage distribution.

6. # Evaluating Policies
For each load balancing policy (pick_first, round_robin, least_load):
Start Consul (if not already running).
Run the LB Server with the desired policy (step 2).
Spawn Backend Servers (step 3).
You can re-use the same backend servers for all tests if they remain running; otherwise, restart them.
Run the Client Scale Test (step 4) and record the output.
Repeat these steps with each policy and compare the printed metrics (response times, throughput, and backend load distribution).

------------------------------------------------------------------------------------------------------------------------------------------

# Consul Starting Error

Error starting agent: error="Failed to start Consul server: Failed to start RPC layer: listen tcp 127.0.0.1:8300: bind: address already in use"

That error indicates that Consul is trying to bind to port 8300, but that port is already in use—often because another Consul agent (or another process) is already running.

Here are some steps to resolve the issue:

Check for an Existing Consul Process:

On Linux or WSL, run:
ps aux | grep consul
or use:
netstat -tulpn | grep 8300
to see which process (PID) is using port 8300.

On Windows, you can use Task Manager or run:
powershell
netstat -ano | findstr :8300
then use Task Manager or taskkill to stop the process if it’s another instance of Consul.

# Terminate the Existing Process (if appropriate):
If you find an already running Consul agent that you don’t need, stop it. For example, on Linux/WSL:
kill <PID>


# Alternative : Use Custom Ports:
If you need to run multiple Consul agents on the same machine or if something else is using port 8300, you can tell Consul to use different ports via command-line options. For example, to run Consul in development mode on alternate ports, you might run:
consul agent -dev -ports="server=8301,serf_lan=8302,serf_wan=8303,http=8500"
This command tells Consul to use port 8301 for its server (RPC) layer instead of the default 8300.

# Restart Consul:
After stopping any conflicting processes or choosing alternate ports, start Consul again:
consul agent -dev