import datetime
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

class nodeItem:
    """ Wrapper to contain instances of a node.
    """
    def __init__(self, **kwargs):
        try:
            self.node_ip = kwargs['node_id']
        except KeyError:
            logging.info(f'nodeItem creation failed. node_ip missing.')
            raise

        self.node_name = kwargs.get('node_name', 'Unnamed')
        self.listen_port = kwargs.get('listen_port', 4812)
        self.busy = kwargs.get('busy', False)

def currentRegistrar():
    """ Retrieve the nodes currently in the registrar.
        
        
    :return: list: list of dicts {'id': <queue message id>, 'node': ``nodeItem``}.
    """
    queue_client = queue.QueueClient.from_connection_string(
        _QUEUE_URL,
        'rosiepi-node-registrar',
        **_QUEUE_CONFIG
    )
    results = queue_client.peek_messages(max_messages=_AZURE_QUEUE_PEEK_MAX)

    node_items = []
    for message in results:
        try:
            kwargs = json.loads(message.content)
            node_items.append(
                {'message_id': message.id, 'node': nodeItem(**kwargs)}
            )
        except:
            logging.info(
                'Failed to process node in registrar. '
                f'Entry malformed: {message.content}'
            )

    return node_items


def addNode(node):
    """ Adds a node to the registrar queue. Each node entry in the 
        registrar will expire an hour after it is added.

    :param: node: The ``nodeItem`` to add to the queue.
    """
    result = True
    if not node.node_ip:
        logging.info(f'addnode failed. node_ip missing.')
        result = False
    else:
        expiration = 3600 # 1 hour

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
            sent_msg = queue_client.send_message(json.dumps(queue_msg),
                                                **{'time_to_live': expiration})
            logging.info(f'Sent the following queue content: {sent_msg.content}')
        except Exception as err:
            logging.info(f'Error sending addnode queue message: {err}')
            result = False

    return result

def updateNode(message_id, node):
    """ Update a node that is currently in the registrar.

    :param: str message_id: The id of the message in the registrar queue
    :param: nodeItem: The ``nodeItem`` with the information to update

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
        sent_msg = queue_client.update_message(message_id,
                                               json.dumps(queue_msg))
        logging.info('Sent the following updated queue content: '
                     f'{sent_msg.content}')
    except Exception as err:
        logging.info(f'Error sending updateNode queue message: {err}')
        result = False

    return result

def pushToNodes(message, stop_on_first_success=False):
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

    active_nodes = currentRegistrar()
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
                    result = updateNode(item['message_id'], node)
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
            


