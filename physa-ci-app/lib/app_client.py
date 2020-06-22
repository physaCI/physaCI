import json
import logging
import os
import requests

import jwt

from datetime import datetime, timedelta

from azure.storage import queue

_CHECK_RUN_UPDATE_PARAMS = [
    'name',
    'details_url',
    'external_id',
    'started_at',
    'status',
    'conclusion',
    'completed_at',
    'output',
    'actions',
]

def generate_jwt_token():
        """ Authenticate with GitHub as an App so that we can
            process API requests
        """
        jwt_auth = None

        logging.info('Generating JWT...')

        utc_now = datetime.utcnow()
        secret = bytes(os.environ['GITHUB_APP_KEY'], encoding='utf-8')
        payload = {
            'iat': utc_now,
            'exp': utc_now + timedelta(minutes=5),
            'iss': os.environ['GITHUB_APP_ID']
        }
        jwt_auth = jwt.encode(payload, secret, algorithm='RS256')

        logging.info(f'JWT generation complete. Successful?: {bool(jwt_auth)}')        

        return jwt_auth

class AppClient():
    """ Client object to wrap and contain necessary functions and variables
        to interact with the App.
    """
    def __init__(self):
        self._payload = None
        self.bearer_token = str(generate_jwt_token(), encoding='utf-8')
        self.installation_token = None

    @property
    def payload(self):
        """ The current payload of the client
        """
        return self._payload

    @payload.setter
    def payload(self, payload):
        self._payload = payload

    def create_installation_app_token(self, payload):
        """ Retrieves a new app installation token to use with App/checks api
        """
        install_token = None
        logging.info(
            'Creating installation app token. '
            f'Bearer token exists?: {bool(self.bearer_token)}'
        )
        if self.bearer_token:
            if self.authenticate_app():
                inst_id = payload['installation']['id']
                url = (
                    'https://api.github.com/app/installations/'
                    f'{inst_id}/access_tokens'
                )
                bearer_string = f'Bearer  {self.bearer_token}'
                header = {
                    'Authorization': bearer_string,
                    'Accept': 'application/vnd.github.machine-man-preview+json'
                }
                response = requests.post(url, headers=header)
                if response.ok:
                    logging.info('Token successfully created.')
                    install_token = response.json()['token']
                else:    
                    logging.info(
                        'Token creation failed. '
                        f'API Response: {response.text}'
                    )

        return install_token

    def authenticate_app(self):
        """ Authenticates the app using the JWT bearer token
        """
        logging.info('Authenticating app...')
        if self.bearer_token:
            url = 'https://api.github.com/app'
            bearer_string = f'Bearer {self.bearer_token}'
            header = {
                'Authorization': bearer_string,
                'Accept': 'application/vnd.github.machine-man-preview+json'
            }
            response = requests.get(url, headers=header)
            if response.ok:
                return True
            else:
                fail_msg = (
                    'App authentication failed.\n'
                    f'Reason: {response.json()["message"]}'
                )
                raise RuntimeError(fail_msg)

class GithubClient(AppClient):
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

    def update_check_run(self, message):
        """ Updates a previously created check run
        """
        update_payload = {'installation': {'id': self.payload['installation_id']}}

        self.installation_token = self.create_installation_app_token(update_payload)
        if not self.installation_token:
            logging.info(
                'Check run not updated. No installation token available.'
            )
            return 401

        
        api_url = self.payload['api_url']

        header = {
            'Authorization': f'token {self.installation_token}',
            'Accept': 'application/vnd.github.antiope-preview+json',
        }
        
        response = requests.patch(api_url, headers=header, json=message)
        final_status = response.status_code
        if not response.ok:
            logging.info(
                'Failed to update check run.\n'
                f'Response: {response.text}\n'
                f'URL: {response.url}\n'
                f'Headers: {response.headers}'
            )
        logging.info(f'Check run update status: {final_status}')
        logging.info(f'Check run update return message: {response.text}')
        
        return final_status