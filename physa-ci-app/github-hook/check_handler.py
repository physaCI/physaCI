from datetime import datetime
import json
import logging
import os
import requests

from azure.storage import queue

# pylint: disable=import-error
from __app__.lib import app_client

class GithubClient(app_client.AppClient):
    """ Client object to wrap and contain necessary functions and variables
        to interact with the App.
    """
    def __init__(self):
        super().__init__()

    def create_check_run(self):
        """ Creates a check run through the API
        """
        logging.info('Creating check run...')
        self.installation_token = self.create_installation_app_token(self.payload)
        if not self.installation_token:
            logging.info(
                'Check run not created. No installation token available.'
            )
            return 401

        repo_name = self.payload['repository']['full_name']
        url = f'https://api.github.com/repos/{repo_name}/check-runs'
        head_sha = None
        if 'check_run' in self.payload:
            head_sha = self.payload['check_run']['head_sha']
        else:
            head_sha = self.payload['check_suite']['head_sha']

        header = {
            'Authorization': f'token {self.installation_token}',
            'Accept': 'application/vnd.github.antiope-preview+json',
        }
        params = {
            'name': 'RosiePi',
            'head_sha': head_sha,
        }
        response = requests.post(url, headers=header, json=params)
        if not response.ok:
            logging.info(
                'Failed to create check run.\n'
                f'Response: {response.text}\n'
                f'URL: {response.url}\n'
                f'Headers: {response.headers}'
            )

        return response.status_code

    def initiate_check_run(self):
        """ Initiates a previously created check run
        """
        logging.info('Initiating check run...')
        self.installation_token = self.create_installation_app_token(self.payload)
        if not self.installation_token:
            logging.info(
                'Check run not initiated. No installation token available.'
            )
            return 401

        repo_name = self.payload['repository']['full_name']
        check_id = self.payload['check_run']['id']
        api_url = f'https://api.github.com/repos/{repo_name}/check-runs/{check_id}'

        header = {
            'Authorization': f'token {self.installation_token}',
            'Accept': 'application/vnd.github.antiope-preview+json',
        }
        params = {
            'name': 'RosiePi',
            'status': 'queued',
            'started_at': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        else:
            logging.info('Creating node-queue message...')
            # generate the queue message for the nodes to act upon
            new_payload = response.json()
            check_suite_id = new_payload['check_suite']['id']
            head_sha = new_payload['head_sha']
            check_run_url = new_payload['html_url']
            check_run_pull_requests = [
                pr['url'] for pr in new_payload['pull_requests']
            ]
            
            queue_msg = {
                'api_url': api_url, # only for dev use (for now)
                'installation_id': str(self.payload['installation']['id']), # only for dev use (for now)
                'check_run_id': str(check_id),
                'check_run_suite_id': str(check_suite_id),
                'check_run_head_sha': str(head_sha),
                'check_run_url': str(check_run_url),
                'check_run_pull_requests': check_run_pull_requests,
                'is_claimed': 'false',
            }

            # using the python library/webapi here so that we can catch
            # any failures and update the check_run accoringly.
            # using binding in 'function.json' would not allow for that.
            queue_url = os.environ['APP_STORAGE_CONN_STR']
            queue_config = {
                'message_encode_policy': queue.TextBase64EncodePolicy(),
                'message_decode_policy': queue.TextBase64DecodePolicy(),
            }
            queue_client = queue.QueueClient.from_connection_string(
                queue_url,
                'rosiepi-check-queue',
                **queue_config
            )

            try:
                encoded_msg = json.dumps(queue_msg)
                sent_msg = queue_client.send_message(encoded_msg)
                logging.info(f'Sent the following queue content: {sent_msg.content}')
            except Exception as err:
                logging.info(f'Error sending node-queue message: {err}')
                final_status = 500
                params = {
                    'status': 'completed',
                    'conclusion': 'failure',
                    'completed_at': datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    'output': {
                        'title': 'RosiePi',
                        'summary': 'Failed',
                        'text': ('RosiePi failed due to an internal error. '
                                 'Please retry. If the problem persists, '
                                 'contact an administrator.')
                    }
                }
                requests.patch(api_url, headers=header, json=params)

        logging.info(f'Check run update successful: {response.ok}')
        
        return final_status