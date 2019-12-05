from datetime import datetime
import logging
import os
import requests

from azure.storage.queue import QueueClient

# pylint: disable=import-error
from __app__.lib import app_client

class testnodeClient(app_client.appClient):
    """ Client object to wrap and contain necessary functions and variables
        to interact with the App.
    """
    def __init__(self):
        super().__init__()

    def update_check_run(self, **kwargs):
        """ Initiates a previously created check run
        """
        logging.info('Updating check run...')
        self.installation_token = self.create_installation_app_token(self.payload)
        if not self.installation_token:
            logging.info(
                'Check run not initiated. No installation token available.'
            )
            return 401

        ## debug state for now. just close the check_run out.
        #repo_name = self.payload['repository']['full_name']
        #check_id = self.payload['check_run']['id']
        repo_name = 'sommersoft/circuitpython'
        check_id = kwargs.get('id', None)
        api_url = f'https://api.github.com/repos/{repo_name}/check-runs/{check_id}'

        header = {
            'Authorization': self.installation_token,
            'Accept': 'application/vnd.github.antiope-preview+json',
        }
        params = {
            'status': 'completed',
            'conclusion': 'neutral',
            'completed_at': datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            'output': {
                'title': 'RosiePi',
                'summary': 'Stopped.',
                'text': ('RosiePi stopped by physaCI.')
            }
        }
        response = requests.patch(api_url, headers=header, json=params)

        return response.status_code