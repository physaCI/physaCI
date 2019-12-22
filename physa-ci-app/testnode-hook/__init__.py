import logging
import os
import re

import azure.functions as func

from . import node_github, node_registrar, node_db

# pylint: disable=import-error
from __app__.lib import result

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    event_status = 200

    req_func = req.route_params.get('func')
    req_action = req.route_params.get('action')

    if req_func == 'addnode':
        node_params = req.get_json()
        ip = req.headers.get('x-forwarded-for')
        ip_extract = re.match(r'((?:[\d]{1,3}\.){3}[\d]{1,3})', ip)
        if ip_extract:
            node_params['node_ip'] = ip_extract.group(1)
        new_node = node_registrar.nodeItem(**node_params)
        result = node_registrar.addNode(new_node)
        if not result:
            event_status = 500
    elif req_func == 'checkresult':
        result_json = req.get_json()
        check_result = result.Result(result_json)
        if not check_result:
            event_status = 500
        else:
            send_to_table = None
            if req_action == 'add':
                send_to_table = node_db.addResult(
                    check_result.resultsToTableEntity()
                )
            elif req_action == 'update':
                send_to_table = node_db.updateResult(
                    check_result.resultsToTableEntity()
                )
            
            if not send_to_table:
                event_status = 500


    return func.HttpResponse(status_code=event_status)