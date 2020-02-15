from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import requests

import jwt

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

def push_to_nodes(message, stop_on_first_success=False):
    """ Push a message to all active, non-busy nodes in the node registrar.
        (Reminder: entries in the registrar queue expire after 1 hour.)
    
    :param: str message: The JSON message to send
    :param: bool stop_on_first_success: Default `False`. Setting to `True`
                                        will cause the push to stop sending
                                        additional push-notifications upon
                                        the first successful response from
                                        a node in the registrar. The queue
                                        message in the registrar will also
                                        be updated to reflect its returned
                                        ``node_busy`` state.

    :return: tuple: A tuple with the overal final_status, and a dict
                    containing any successful responses from nodes.
    """

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
    final_status = 200
    push_response = {}
    for item in active_nodes:
        node = item['node']
        if node.busy:
            continue
        
        header = {
            'media': 'application/json'
        }
        response = requests.post(
            f'http://{node.node_ip}:{node.listen_port}/', #update after flask is setup on the RPi
            headers=header,
            json=message,
        )
        
        final_status = response.status_code
        body = response.json()
        body['status_code'] = response.status_code
        push_response[node.node_ip] = body
        if response.ok:
            if stop_on_first_success:
                 node.busy = body['node_busy']
                 result = update_node(
                     item['message'], node, {'status_code': 200, 'body': 'OK'}
                )
                 if result['status_code'] < 400: # update success; stop pushing messages
                    break 

                 else:
                    logging.info(
                        'updateNode failed during pushToNodes.\n'
                        f'Response info: {body}\n'
                        f'Node info: {node}\n'
                        f'Error info: {err}'
                    )

    return final_status, push_response
            


