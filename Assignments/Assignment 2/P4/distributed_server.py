import grpc
from concurrent import futures
import time
import logging
from collections import Counter
import argparse

import byzantine_pb2
import byzantine_pb2_grpc

def setup_logging(general_id):
    # Use a fixed log file name.
    log_filename = f'general_{general_id}_intermediate.log'
    logger = logging.getLogger(f'general_{general_id}')
    logger.setLevel(logging.INFO)
    # Remove any existing handlers.
    if logger.hasHandlers():
        logger.handlers.clear()
    # Create a new file handler in write mode (this clears the file).
    fh = logging.FileHandler(log_filename, mode='w')
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    # Store filename on logger for later resetting.
    logger.log_filename = log_filename
    return logger

class General:
    def __init__(self, id, is_traitor, peers):
        self.id = id
        self.is_traitor = is_traitor
        # peers: list of tuples (peer_id, address)
        self.peers = peers  
        self.orders = []
        self.logger = setup_logging(id)

    def reset_log(self):
        # Clear the log file by removing handlers and reattaching a new handler in 'w' mode.
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        fh = logging.FileHandler(self.logger.log_filename, mode='w')
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        self.logger.info("Log file reset for general %d", self.id)

    def _next_order(self, order, index):
        # Traitors flip the order for even-indexed recipients.
        if self.is_traitor:
            if index % 2 == 0:
                flipped = "ATTACK" if order == "RETREAT" else "RETREAT"
                self.logger.info("General %d (traitor) flipping order at index %d: %s -> %s", 
                                 self.id, index, order, flipped)
                return flipped
        return order

    def process_order(self, commander_id, t, order, sender_id):
        # Use the mapping: printed_round = 4 - t
        self.logger.info("General %d received order '%s' at round %d from commander %d (sender %d)", 
                         self.id, order, 4 - t - 1, commander_id, sender_id)
        if t < 0:
            self.orders.append(order)
            self.logger.info("General %d appending order '%s' (base case)", self.id, order)
        elif t == 0:
            for index, (peer_id, peer_address) in enumerate(self.peers):
                new_order = self._next_order(order, index)
                self.send_order_to_peer(commander_id, t - 1, new_order, peer_id)
        else:
            for index, (peer_id, peer_address) in enumerate(self.peers):
                if peer_id != self.id and peer_id != commander_id:
                    new_order = self._next_order(order, index)
                    self.send_order_to_peer(commander_id, t - 1, new_order, peer_id)

    def send_order_to_peer(self, commander_id, t, order, peer_id):
        # Look up the peer’s address.
        peer_address = None
        for pid, addr in self.peers:
            if pid == peer_id:
                peer_address = addr
                break
        if peer_address is None:
            self.logger.error("General %d: peer %d not found", self.id, peer_id)
            return

        try:
            channel = grpc.insecure_channel(peer_address)
            stub = byzantine_pb2_grpc.ByzantineServiceStub(channel)
            request = byzantine_pb2.OrderMessage(
                commander_id=commander_id,
                sender_id=self.id,
                recursion_level=t,
                order=order
            )
            stub.SendOrder(request)
        except Exception as e:
            self.logger.error("Error sending order from general %d to peer %d at %s: %s", 
                              self.id, peer_id, peer_address, str(e))

class ByzantineServiceServicer(byzantine_pb2_grpc.ByzantineServiceServicer):
    def __init__(self, general):
        self.general = general

    def RunAlgorithm(self, request, context):
        # When a new algorithm run is initiated by the commander, reset this general's log.
        self.general.reset_log()
        self.general.logger.info("RunAlgorithm called on general %d with t: %d, order: %s", 
                                   self.general.id, request.t, request.order)
        # Only the commander (general id 0) may run RunAlgorithm.
        if self.general.id != 0:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details("Only the commander (id 0) can run RunAlgorithm")
            return byzantine_pb2.AlgorithmResponse()
        self.general.process_order(commander_id=self.general.id, t=request.t, order=request.order, sender_id=self.general.id)
        # Return decision tally for the commander.
        decision_votes = []
        c = Counter(self.general.orders)
        for order_value, count in c.most_common():
            vote = byzantine_pb2.Vote(order=order_value, count=count)
            decision_votes.append(vote)
        response = byzantine_pb2.AlgorithmResponse(decisions=[
            byzantine_pb2.Decision(general_id=self.general.id, votes=decision_votes)
        ])
        return response

    def SendOrder(self, request, context):
        # Log with the new mapping: printed_round = 4 - request.recursion_level
        self.general.logger.info("SendOrder received at general %d: order '%s' at round %d from commander %d (sender %d)", 
                                   self.general.id, request.order, 4 - request.recursion_level - 1, request.commander_id, request.sender_id)
        self.general.process_order(commander_id=request.commander_id, t=request.recursion_level, order=request.order, sender_id=request.sender_id)
        return byzantine_pb2.Empty()

    def GetDecision(self, request, context):
        c = Counter(self.general.orders)
        decision_votes = []
        for order_value, count in c.most_common():
            vote = byzantine_pb2.Vote(order=order_value, count=count)
            decision_votes.append(vote)
        return byzantine_pb2.Decision(general_id=self.general.id, votes=decision_votes)

    def ResetLog(self, request, context):
        self.general.reset_log()
        return byzantine_pb2.Empty()

def serve_general(general_id, port, is_traitor, peers):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    general = General(general_id, is_traitor, peers)
    servicer = ByzantineServiceServicer(general)
    byzantine_pb2_grpc.add_ByzantineServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f'[::]:{port}')
    general.logger.info("Starting general server %d on port %d", general_id, port)
    server.start()
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)
        general.logger.info("Stopping general server %d", general_id)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Distributed Byzantine General Server")
    parser.add_argument("--id", type=int, required=True, help="General ID")
    parser.add_argument("--port", type=int, required=True, help="Port to listen on")
    parser.add_argument("--traitor", action="store_true", help="Mark this general as traitor")
    parser.add_argument("--peers", type=str, required=True, 
                        help="Comma-separated list of peer addresses in the format id:host:port")
    args = parser.parse_args()

    # Parse peers argument into a list of (peer_id, address) tuples.
    peers = []
    for peer_str in args.peers.split(','):
        parts = peer_str.split(':')
        if len(parts) == 3:
            peer_id = int(parts[0])
            host = parts[1]
            port = parts[2]
            address = f'{host}:{port}'
            peers.append((peer_id, address))
    serve_general(args.id, args.port, args.traitor, peers)
