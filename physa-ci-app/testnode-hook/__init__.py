import json
import logging
import os
import re

import azure.functions as func

# pylint: disable=import-error
from __app__.lib import result, node_github, node_registrar, node_db

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    response_kwargs = {
        'status_code': 200,
        'body': 'OK',
        'headers': {},
    }

    req_func = req.route_params.get('func')
    req_action = req.route_params.get('action')

    if req_func == 'registrar':
        node_params = req.get_json()
        logging.info(f'node_params: {node_params}')
        
        ip = req.headers.get('x-forwarded-for', "null")
        ip_extract = re.match(r'((?:[\d]{1,3}\.){3}[\d]{1,3})', ip)
        if ip_extract:
            logging.info(f'ip_extract: {ip_extract.group(1)}')
            node_params['node_ip'] = ip_extract.group(1)

        if req_action == 'add':
                response_kwargs = node_registrar.add_node(node_params, response_kwargs)
        elif req_action == 'update':
            req_node = node_registrar.NodeItem(**node_params)
            nodes = node_registrar.current_registrar()
            for node in nodes:
                if (node['node_name'] == req_node.node_name and
                    node['node_ip'] == req_node.node_ip):
                        response_kwargs = node_registrar.update_node(
                            node['message'], req_node, response_kwargs
                        )
                        break

    elif req_func == 'testresult':
        result_json = req.get_json()
        check_result = result.Result(result_json)
        if not check_result:
            response_kwargs['status_code'] = 400
            response_kwargs['body'] = (
                'Bad Request. Request missing JSON payload.'
            )
        else:
            send_to_table = None
            if req_action == 'add':
                send_to_table = node_db.add_result(
                    check_result.results_to_table_entity()
                )
            elif req_action == 'update':
                send_to_table = node_db.update_result(
                    check_result.results_to_table_entity()
                )
            
            if not send_to_table:
                response_kwargs['status_code'] = 500
                response_kwargs['body'] = (
                    'Interal error. Failed to update test results in physaCI.'
                )


    return func.HttpResponse(**response_kwargs)
