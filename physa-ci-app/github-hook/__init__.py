import logging
import os

import azure.functions as func

# pylint: disable=import-error
from __app__.lib import app_client

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    
    #logging.info('Header Info:')
    #for item in req.headers:
    #    logging.info("\t{}: {}".format(item, req.headers[item]))

    event_status = 200

    if 'x-github-event' in req.headers:
        event_client = app_client.GithubClient()
        event = req.headers['x-github-event']
        payload = ""
        action = None
        try:
            payload = req.get_json()
            if payload:
                logging.info(f'Payload: {payload}')
                action = payload.get('action', None)
                event_client.payload = payload
        except ValueError:
            logging.info('Failed to retrieve event payload.')
            event = None
        
        logging.info(f'Payload received. event type: {event}, action: {action}')        
        
        if not event:
            event_status = 500        
        
        elif event == 'check_suite':
            logging.info('Processing check_suite...')
            if (action in ('requested', 'rerequested') and
                payload.get('check_suite', {}).get('pull_requests')):
                    # create check_run
                    event_status = event_client.create_check_run()
        
        elif event == 'check_run':
            logging.info('Processing check_run...')
            if str(payload['check_run']['app']['id']) == os.environ['GITHUB_APP_ID']:
                if action == 'created':
                    # initiate check_run
                    event_status = event_client.initiate_check_run()
                elif action == 'rerequested':
                    # create check_run
                    event_status = event_client.create_check_run()
            else:
                check_id = str(payload['check_run']['app']['id'])
                os_id = os.environ['GITHUB_APP_ID']
                logging.info(f'Failed to match app IDs. env var: {os_id}; payload: {check_id}')

    logging.info(f'Event status: {event_status}')
    return func.HttpResponse(status_code=event_status)


    