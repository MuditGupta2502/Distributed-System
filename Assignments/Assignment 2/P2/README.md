# 1. Generate gRPC Code:

Make sure you have the grpcio and grpcio-tools packages installed. Then generate the Python code from the proto files (run these commands from the project root):

python -m grpc_tools.protoc -I./protofiles --python_out=. --grpc_python_out=. ./protofiles/mapper_service.proto
python -m grpc_tools.protoc -I./protofiles --python_out=. --grpc_python_out=. ./protofiles/reducer_service.proto

This will create mapper_service_pb2.py, mapper_service_pb2_grpc.py, reducer_service_pb2.py, and reducer_service_pb2_grpc.py in your project root (or adjust the paths as needed).


# 2. Start the Master (Client):
Run the master script from the client/ folder. For example:
cd client
python master.py

Follow the prompts to select the query (1 for Word Count or 2 for Inverted Index), specify the number of mappers and reducers, and provide the ports for each.


# 3. Review the Output:
The final output files will be written to the output/ folder. Intermediate mapper outputs are stored in the folders/ directory.
