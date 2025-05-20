import grpc
import argparse
import byzantine_pb2
import byzantine_pb2_grpc

def reset_log(host, port):
    channel = grpc.insecure_channel(f'{host}:{port}')
    stub = byzantine_pb2_grpc.ByzantineServiceStub(channel)
    stub.ResetLog(byzantine_pb2.Empty())

def get_decision(host, port):
    channel = grpc.insecure_channel(f'{host}:{port}')
    stub = byzantine_pb2_grpc.ByzantineServiceStub(channel)
    decision = stub.GetDecision(byzantine_pb2.Empty())
    return decision

def run(order, t, num_generals, base_port, host, generals_input):
    # First, reset logs on all servers.
    for i in range(num_generals):
        port = base_port + i
        reset_log(host, port)
    
    # Trigger the algorithm on the commander (general 0).
    channel = grpc.insecure_channel(f'{host}:{base_port}')
    stub = byzantine_pb2_grpc.ByzantineServiceStub(channel)
    request = byzantine_pb2.AlgorithmRequest(
        t=t,
        order=order,
        generals=[]  # Not used in distributed version.
    )
    stub.RunAlgorithm(request)
    
    # Wait briefly for the algorithm to propagate.
    import time
    time.sleep(3)
    
    # Collect decisions from all generals.
    print("Vote tallies from generals:")
    loyal_final_decisions = []
    loyalty = [spec.strip().lower() for spec in generals_input.split(',')]
    for i in range(num_generals):
        port = base_port + i
        decision = get_decision(host, port)
        print(f"General {decision.general_id}:")
        general_final = "No decision"
        if decision.votes:
            # Display each vote tally.
            for vote in decision.votes:
                print(f"  {vote.order}: {vote.count}")
            general_final = decision.votes[0].order
        else:
            print("  No decision recorded.")
        # Only consider loyal generals for consensus.
        if i < len(loyalty) and loyalty[i] == "l":
            loyal_final_decisions.append(general_final)
    
    # Compute and print final consensus.
    if loyal_final_decisions:
        consensus = loyal_final_decisions[0]
        if all(dec == consensus for dec in loyal_final_decisions):
            print("\nFinal consensus reached:", consensus)
        else:
            print("\nNo consensus reached among loyal generals.")
    else:
        print("\nNo loyal generals provided.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Distributed Byzantine Generals Client")
    parser.add_argument("--order", type=str, required=True, help="The order to send (ATTACK or RETREAT)")
    parser.add_argument("--t", type=int, required=True, help="Recursion depth (max traitors tolerated)")
    parser.add_argument("--num_generals", type=int, required=True, help="Total number of generals")
    parser.add_argument("--base_port", type=int, default=50051, help="Base port where servers are running")
    parser.add_argument("--host", type=str, default="localhost", help="Host for servers")
    parser.add_argument("--generals", type=str, required=True, 
                        help="Comma-separated list of generals (l for loyal, t for traitor), e.g., l,l,l,t,t,l,l,t,l,l")
    args = parser.parse_args()
    run(args.order, args.t, args.num_generals, args.base_port, args.host, args.generals)
