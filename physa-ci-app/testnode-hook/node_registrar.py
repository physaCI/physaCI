import hmac
import json
import logging
import os
import requests

from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from socket import gethostname

from azure.storage import queue

_AZURE_QUEUE_PEEK_MAX = 32

_QUEUE_URL = os.environ['APP_STORAGE_CONN_STR']
_QUEUE_CONFIG = {
    'message_encode_policy': queue.TextBase64EncodePolicy(),
    'message_decode_policy': queue.TextBase64DecodePolicy(),
}

@dataclass(eq=False)
class NodeItem:
    """ Wrapper to contain instances of a node.
    """
    node_ip: str = None
    node_sig_key: str = None
    node_name: str = 'Unnamed'
    listen_port: int = 4812
    busy: bool = False

def node_in_registrar(node_ip, node_name, registrar_entries):
    """ Checks if a node already exists in the registrar

    :param: node_ip: The IP address of the new node
    :param: node_name: The name of the new node
    :param: registrar_entries: A list of the current registrar entries
                               from ``current_registrar()``

    :return: bool: If the new node_ip and node_name are in the registrar
    """
    registrar_ips_and_names = [
        (entry['node'].node_ip, entry['node'].node_name)
        for entry in registrar_entries
    ]

    return (node_ip, node_name) in registrar_ips_and_names


def process_dup_node(node, current_entries):
    """ Processes a request for adding a node to the queue, that is
        already in the queue and not expired.

    :param: node: The new ``NodeItem`` being added
    :param: current_entries: A list of the current registrar entries
                             from ``current_registrar()``

    :return: status_code, body: The result of processing the new node,
                                as updates to the HTTP response
                                
    """
    status_code = 200
    body = 'OK'
    for entry in current_entries:
        entry_node_ip = entry['node'].node_ip
        entry_node_name = entry['node'].node_name

        if node.node_name == entry_node_name:
            if node.node_ip == entry_node_ip:
                logging.info(f'Node exists in queue: {entry}')
                entry_expires = entry['message'].expires_on
                expire_window = datetime.now(timezone.utc) + timedelta(minutes=5)
                if entry_expires < expire_window:
                    remove_node(entry['message'])
                else:
                    status_code = 409
                    body = (
                        'Request to add node made for existing node that '
                        'is not expiring within 5 minutes. Aborting...'
                    )
                    logging.info(body + f'\nnode info: {entry["node"]}')
                    break
            else:
                status_code = 409
                body = (
                    'Request to add node made for existing node with '
                    'a different IP address. Disregarding...'
                )
                logging.info(body + f'\nnode info: {entry["node"]}')
                break

    return status_code, body

def current_registrar():
    """ Retrieve the nodes currently in the registrar.
        
        
    :return: list: list of dicts 
                   {'message': queue.QueueMessage,
                    'node': ``nodeItem``}.
    """
    queue_client = queue.QueueClient.from_connection_string(
        _QUEUE_URL,
        'rosiepi-node-registrar',
        **_QUEUE_CONFIG
    )
    msg_kwargs = {
        'messages_per_page': _AZURE_QUEUE_PEEK_MAX,
        'visibility_timeout': 1
    }
    #results = queue_client.peek_messages(max_messages=_AZURE_QUEUE_PEEK_MAX)
    results = queue_client.receive_messages(**msg_kwargs)

    node_items = []
    for message in results:
        try:
            kwargs = json.loads(message.content)
            node_items.append(
                {
                    'message': message,
                    'node': NodeItem(**kwargs),
                }
            )
        except:
            logging.info(
                'Failed to process node in registrar. '
                f'Entry malformed: {message.content}'
            )

    return node_items


def add_node(node_params, response):
    """ Adds a node to the registrar queue. Each node entry in the 
        registrar will expire an hour after it is added. If supplied
        node is already in the registrar queue and set to expire within
        5 minutes, it will be removed from the queue before adding the
        new entry.

    :param: node: The ``nodeItem`` to add to the queue.
    :param: dict response: A dict to hold the results for sending
                           the response message

    :returns: dict response: The HTTP response message
    """

    node = NodeItem(**node_params)
    if not node.node_ip:
        response['status_code'] = 400
        response['body'] = 'Could not parse requesting node\'s IP address.'
    elif not node.node_sig_key:
        response['status_code'] = 400
        response['body'] = 'Could not parse requesting node\'s signature key.'
    else:
        current_entries = current_registrar()
        if node_in_registrar(node.node_ip, node.node_name, current_entries):
            response['status_code'], response['body'] = (
                process_dup_node(node, current_entries)
            )

        if response['status_code'] < 400:
            queue_msg = {
                'node_name': node.node_name,
                'node_ip': node.node_ip,
                'node_sig_key': node.node_sig_key,
                'listen_port': node.listen_port,
                'busy': node.busy,
            }

            queue_client = queue.QueueClient.from_connection_string(
                _QUEUE_URL,
                'rosiepi-node-registrar',
                **_QUEUE_CONFIG
            )
            expiration = 3600 # 1 hour
            ttl = {'time_to_live': expiration}
            try:
                sent_msg = queue_client.send_message(json.dumps(queue_msg),
                                                     **ttl)
                logging.info(f'Sent the following queue content: {sent_msg.content}')
            except Exception as err:
                response['status_code'] = 500
                response['body'] = (
                    'Interal error. Failed to add node to physaCI registrar.'
                )
                logging.info(f'Error sending addnode queue message: {err}')

    return response

def update_node(message, node, response):
    """ Update a node that is currently in the registrar.

    :param: str message: The id of the message in the registrar queue
    :param: nodeItem: The ``NodeItem`` with the information to update
    :param: dict response: A dict to hold the results for sending
                           the response message

    :return: dict response: The HTTP response message
    """

    queue_msg = {
        'node_name': node.node_name,
        'node_ip': node.node_id,
        'node_sig_key': node.node_sig_key,
        'listen_port': node.listen_port,
        'busy': node.busy,
    }

    queue_client = queue.QueueClient.from_connection_string(
        _QUEUE_URL,
        'rosiepi-node-registrar',
        **_QUEUE_CONFIG
    )
    try:
        sent_msg = queue_client.update_message(message,
                                               json.dumps(queue_msg))
        logging.info('Sent the following updated queue content: '
                     f'{sent_msg.content}')
    except Exception as err:
        response['status_code'] = 500
        response['body'] = (
            'Interal error. Failed to update node in physaCI registrar.'
        )
        logging.info(f'Error sending updateNode queue message: {err}')
        

    return response

def remove_node(message):
    """ Remove a node from the queue.

    :param: queue.QueueMessage message: The message in the registrar queue

    :return: bool: Result of the removal.
    """
    result = True

    queue_client = queue.QueueClient.from_connection_string(
        _QUEUE_URL,
        'rosiepi-node-registrar',
        **_QUEUE_CONFIG
    )
    try:
        delete_msg = queue_client.delete_message(message)
        logging.info('Sent the following message to delete: '
                     f'{delete_msg}')
    except Exception as err:
        logging.info(f'Error sending remove_node queue message: {err}')
        result = False

    return result

def push_test_to_nodes(message):
    """ Push a test request to all nodes in the node registrar.
        (Reminder: entries in the registrar queue expire after 1 hour.)
    
    :param: str message: The JSON message to send

    :return: bool job_accepted: 
    """

    def _send_run_test_request(node, message):
        """ Private function to handle sending HTTP requests to nodes,
            and updating the registrar.
        """
        response = None
        
        header = {'media': 'application/json'}
        
        try:
            response = requests.post(
                f'http://{node.node_ip}:{node.listen_port}/run-test',
                auth=SigAuth(node),
                headers=header,
                json=message,
            )
        except requests.ConnectionError:
            logging.warning(
                'push_to_nodes connection error:\n'
                f'\tNode name: {node.node_name}\n'
                f'\tNode IP: {node.node_ip}'
            )
        
        if response:
            body = response.json()
            body['status_code'] = response.status_code
            push_response[node.node_ip] = body
            if response.ok:
                node.busy = body['node_busy']
                result = update_node(
                    item['message'], node, {'status_code': 200, 'body': 'OK'}
                )
                if not result['status_code'] < 400:
                    logging.info(
                        'update_node failed during push_test_to_nodes.\n'
                        f'Response info: {body}\n'
                        f'Node info:\n'
                        f'\tName: {node.node_name}'
                        f'\tIP: {node.node_ip}'
                    )

        return response

    
    try:
        json.loads(message)
    except Exception as err:
        logging.info(
            'Failed to push message to nodes. JSON format incorrect.\n'
            f'Message: {message}\n'
            f'Exception: {err}'
        )
        return False

    active_nodes = current_registrar()

    push_response = {}
    busy_nodes = []
    job_accepted = False

    for item in active_nodes:
        node = item['node']
        # prefer non-busy nodes, but stash busy nodes to fallback on
        if node.busy:
            busy_nodes.append(item)
            continue
        
        response = _send_run_test_request(node, message)
        if not response:
            continue
        else:
            if response.ok:
                job_accepted = True
                break
        
    # fallback to adding a test request to a busy node's queue
    # starting with the node with the fewest queued jobs
    if not job_accepted:
        for item in busy_nodes:
            node = item['node']
                        
            try:
                response = requests.get(
                    f'http://{node.node_ip}:{node.listen_port}/status',
                    auth=SigAuth(node)
                )
            except requests.ConnectionError:
                continue

            if response.ok:
                status = response.json()
                item['node_job_count'] = status.get('job_count', 999)

        busy_nodes.sort(key=lambda count: count.get('node_job_count', 999))
        for item in busy_nodes:
            response = _send_run_test_request(node, message)
            if not response:
                continue
            else:
                if response.ok:
                    job_accepted = True
                    break

    return job_accepted

class SigAuth(requests.auth.AuthBase):
    def __init__(self, node):
        self.node = node

    def __call__(self, r):
        signature, included_headers = self._build_sig(r.method, r.url_path)
        r.headers['Authorization'] = signature
        r.headers.update(included_headers)

        return r

    def _build_sig(self, http_method, http_path):
        """ Build the HTTP headers with a signature for authentication with
            a node's server.

        :param: str http_method: The HTTP request method (e.g. GET, POST)
        :param: str http_path: The target path of the HTTP request
                            (e.g. '/status')

        :return: str signature: 
        """
        request_target = f'{http_method.lower()} {http_path}'
        header = {
            'Host': gethostname(),
            'Date': datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT'),
        }

        sig_header_keys = ' '.join([hdr.lower() for hdr in header.keys()])
        sig_string = (f'(request-target) {request_target}\nhost: {header["Host"]}\n'
                    f'date: {header["Date"]}')
        sig_hashed = hmac.new(
            self.node.node_sig_key,
            msg=sig_string.encode(),
            digestmod=sha256
        )

        signature = ''.join([
            'Signature '
            f'keyID="{gethostname()}",',
            'algorithm="hmac-sha256",',
            f'headers="(request-target) {sig_header_keys}",',
            f'signature="{b64encode(sig_hashed.digest())}"'
        ])


        return signature, header