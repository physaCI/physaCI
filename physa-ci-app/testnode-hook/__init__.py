import json
import logging
import os
import re

import azure.functions as func

# pylint: disable=import-error
from __app__.lib import app_client, result, node_github, node_registrar, node_db

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

        if req_action == 'update':
            find_entity = node_db.get_result(
                result_json['node_name'],
                result_json['check_run_id'],
                **{
                    'accept': 'application/json;odata=nometadata',
                    'timeout': 120
                }
            )
            
            logging.info(f'find_entity from table: {find_entity}')

            if find_entity is not None:
                for key, value in result_json.get('github_data', {}).items():
                    new_key = f'check_run_{key}'
                    find_entity.update({new_key: value})

                find_entity.update(
                    {'node_results': result_json.get('node_test_data', {}).get('board_tests')}
                )

                logging.info(f'find_entity after updates: {find_entity}')

                result_json = find_entity


        check_result = result.Result(result_json)
        if not check_result.results:
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

            check_result_github = json.loads(check_result.results_to_github())
            github_check_message = {}
            for param in app_client._CHECK_RUN_UPDATE_PARAMS:
                if param in check_result_github:
                    github_check_message.update(
                        {param: check_result_github[param]}
                    )

            logging.info(
                'Updating GitHub check run with the following: '
                f'{github_check_message}'
            )

            event_client = app_client.GithubClient()
            event_client.payload = check_result.results
            event_client.update_check_run(github_check_message)

    return func.HttpResponse(**response_kwargs)
