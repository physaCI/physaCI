from datetime import datetime
import json
import logging
import os
import requests
import time

import azure.functions as func

# pylint: disable=import-error
from __app__.lib import app_client

class DevGithubClient(app_client.appClient):
    """ Client object to wrap and contain necessary functions and variables
        to interact with the App.
    """
    def __init__(self):
        super().__init__()

    def close_check_run(self):
        """ Initiates a previously created check run
        """
        logging.info('[dev] Closing check run...')

        dev_payload = {'installation': {'id': self.payload['installation_id']}}

        self.installation_token = self.create_installation_app_token(dev_payload)
        if not self.installation_token:
            logging.info(
                '[dev] Check run not initiated. No installation token available.'
            )
            return 401

        
        api_url = self.payload['api_url']

        header = {
            'Authorization': f'token {self.installation_token}',
            'Accept': 'application/vnd.github.antiope-preview+json',
        }
        params = {
            'status': 'completed',
            'conclusion': 'failure',
            'completed_at': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            'output': {
                'title': 'RosiePi',
                'summary': 'Completed',
                'text': ('Check run closed by dev-close-check.')
            }
        }
        response = requests.patch(api_url, headers=header, json=params)
        final_status = response.status_code
        if not response.ok:
            logging.info(
                'Failed to update check run.\n'
                f'Response: {response.text}\n'
                f'URL: {response.url}\n'
                f'Headers: {response.headers}'
            )
        logging.info(f'[dev] Check run close status: {final_status}')
        logging.info(f'[dev] Check run close return message: {response.text}')
        return final_status

def main(msg: func.QueueMessage) -> None:
    logging.info(
        f'[dev] Python queue trigger function processed a queue item.'
    )
    message = msg.get_body().decode()
    logging.info(f'[dev] message is: {message}')
    logging.info('[dev] Sleeping for 1 minute, then will close check_run...')
    time.sleep(60)

    check_info = json.loads(message)
    
    event_client = DevGithubClient()
    event_client.payload = check_info

    event_client.close_check_run()



