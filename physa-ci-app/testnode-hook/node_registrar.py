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

class NodeItem:
    """ Wrapper to contain instances of a node.
    """
    def __init__(self, **kwargs):
        try:
            self.node_ip = kwargs['node_ip']
        except KeyError:
            logging.info(f'nodeItem creation failed. node_ip missing.')
            raise

        self.node_name = kwargs.get('node_name', 'Unnamed')
        self.listen_port = kwargs.get('listen_port', 4812)
        self.busy = kwargs.get('busy', False)

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


def add_node(node):
    """ Adds a node to the registrar queue. Each node entry in the 
        registrar will expire an hour after it is added. If supplied
        node is already in the registrar queue and set to expire within
        5 minutes, it will be removed from the queue before adding the
        new entry.

    :param: node: The ``nodeItem`` to add to the queue.
    """
    result = True
    if not node.node_ip:
        logging.info(f'addnode failed. node_ip missing.')
        result = False
    else:
        current_entries = current_registrar()
        for entry in current_entries:
            entry_node_ip = entry['node'].node_ip
            entry_node_name = entry['node'].node_name

            if (node.node_ip == entry_node_ip and
                node.node_name == entry_node_name):
                    logging.info(f'Node exists in queue: {entry}')
                    entry_expires = entry['message'].expires_on
                    expire_window = datetime.now(timezone.utc) + timedelta(minutes=5)
                    if entry_expires < expire_window:
                        remove_node(entry['message'])
                    else:
                        logging.info(
                            'add_node request made for existing node that '
                            'is not expiring within 5 minutes. Aborting...'
                            f'node info: {entry["node"]}'
                        )
                        result = False

        if result:
            queue_msg = {
                'node_name': node.node_name,
                'node_ip': node.node_ip,
                'listen_port': node.listen_port,
                'busy': node.busy,
            }

            queue_client = queue.QueueClient.from_connection_string(
                _QUEUE_URL,
                'rosiepi-node-registrar',
                **_QUEUE_CONFIG
            )
            expiration = 3600 # 1 hour
            try:
                sent_msg = queue_client.send_message(json.dumps(queue_msg),
                                                    **{'time_to_live': expiration})
                logging.info(f'Sent the following queue content: {sent_msg.content}')
            except Exception as err:
                logging.info(f'Error sending addnode queue message: {err}')
                result = False

    return result

def update_node(message, node):
    """ Update a node that is currently in the registrar.

    :param: str message: The id of the message in the registrar queue
    :param: nodeItem: The ``NodeItem`` with the information to update

    :return: bool: Result of the update
    """
    result = True
    queue_msg = {
        'node_name': node.node_name,
        'node_ip': node.node_id,
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
        logging.info(f'Error sending updateNode queue message: {err}')
        result = False

    return result

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

def push_to_todes(message, stop_on_first_success=False):
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
                try:
                    node.busy = body['node_busy']
                    result = update_node(item['message'], node)
                    if result: # update success; stop pushing messages
                       break 
                except Exception as err:
                    logging.info(
                        'updateNode failed during pushToNodes.\n'
                        f'Response info: {body}\n'
                        f'Node info: {node}\n'
                        f'Error info: {err}'
                    )

    return final_status, push_response
            


