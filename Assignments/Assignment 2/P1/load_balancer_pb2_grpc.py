# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc
import warnings

import load_balancer_pb2 as load__balancer__pb2

GRPC_GENERATED_VERSION = '1.70.0'
GRPC_VERSION = grpc.__version__
_version_not_supported = False

try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True

if _version_not_supported:
    raise RuntimeError(
        f'The grpc package installed is at version {GRPC_VERSION},'
        + f' but the generated code in load_balancer_pb2_grpc.py depends on'
        + f' grpcio>={GRPC_GENERATED_VERSION}.'
        + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}'
        + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.'
    )


class LoadBalancerStub(object):
    """Services
    """

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.RegisterBackend = channel.unary_unary(
                '/loadbalancer.LoadBalancer/RegisterBackend',
                request_serializer=load__balancer__pb2.BackendInfo.SerializeToString,
                response_deserializer=load__balancer__pb2.RegisterResponse.FromString,
                _registered_method=True)
        self.ReportLoad = channel.unary_unary(
                '/loadbalancer.LoadBalancer/ReportLoad',
                request_serializer=load__balancer__pb2.LoadReport.SerializeToString,
                response_deserializer=load__balancer__pb2.RegisterResponse.FromString,
                _registered_method=True)
        self.GetBackend = channel.unary_unary(
                '/loadbalancer.LoadBalancer/GetBackend',
                request_serializer=load__balancer__pb2.ServerRequest.SerializeToString,
                response_deserializer=load__balancer__pb2.BackendInfo.FromString,
                _registered_method=True)


class LoadBalancerServicer(object):
    """Services
    """

    def RegisterBackend(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def ReportLoad(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def GetBackend(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_LoadBalancerServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'RegisterBackend': grpc.unary_unary_rpc_method_handler(
                    servicer.RegisterBackend,
                    request_deserializer=load__balancer__pb2.BackendInfo.FromString,
                    response_serializer=load__balancer__pb2.RegisterResponse.SerializeToString,
            ),
            'ReportLoad': grpc.unary_unary_rpc_method_handler(
                    servicer.ReportLoad,
                    request_deserializer=load__balancer__pb2.LoadReport.FromString,
                    response_serializer=load__balancer__pb2.RegisterResponse.SerializeToString,
            ),
            'GetBackend': grpc.unary_unary_rpc_method_handler(
                    servicer.GetBackend,
                    request_deserializer=load__balancer__pb2.ServerRequest.FromString,
                    response_serializer=load__balancer__pb2.BackendInfo.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'loadbalancer.LoadBalancer', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('loadbalancer.LoadBalancer', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class LoadBalancer(object):
    """Services
    """

    @staticmethod
    def RegisterBackend(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/loadbalancer.LoadBalancer/RegisterBackend',
            load__balancer__pb2.BackendInfo.SerializeToString,
            load__balancer__pb2.RegisterResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def ReportLoad(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/loadbalancer.LoadBalancer/ReportLoad',
            load__balancer__pb2.LoadReport.SerializeToString,
            load__balancer__pb2.RegisterResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)

    @staticmethod
    def GetBackend(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/loadbalancer.LoadBalancer/GetBackend',
            load__balancer__pb2.ServerRequest.SerializeToString,
            load__balancer__pb2.BackendInfo.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)


class ComputeStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.ComputeTask = channel.unary_unary(
                '/loadbalancer.Compute/ComputeTask',
                request_serializer=load__balancer__pb2.TaskRequest.SerializeToString,
                response_deserializer=load__balancer__pb2.TaskResponse.FromString,
                _registered_method=True)


class ComputeServicer(object):
    """Missing associated documentation comment in .proto file."""

    def ComputeTask(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_ComputeServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'ComputeTask': grpc.unary_unary_rpc_method_handler(
                    servicer.ComputeTask,
                    request_deserializer=load__balancer__pb2.TaskRequest.FromString,
                    response_serializer=load__balancer__pb2.TaskResponse.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'loadbalancer.Compute', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('loadbalancer.Compute', rpc_method_handlers)


 # This class is part of an EXPERIMENTAL API.
class Compute(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def ComputeTask(request,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.unary_unary(
            request,
            target,
            '/loadbalancer.Compute/ComputeTask',
            load__balancer__pb2.TaskRequest.SerializeToString,
            load__balancer__pb2.TaskResponse.FromString,
            options,
            channel_credentials,
            insecure,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
            _registered_method=True)
