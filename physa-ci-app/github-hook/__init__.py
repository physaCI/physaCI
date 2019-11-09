import datetime
import json
import logging
import os
import requests

import azure.functions as func
import jwt


def generate_jwt_token():
        """ Authenticate with GitHub as an App so that we can
            process API requests
        """
        utc_now = datetime.datetime.utcnow()
        payload = {
            'iat': utc_now,
            'exp': utc_now + datetime.timedelta(minutes=5),
            'iss': os.environ['APP_ID']
        }
        jwt_auth = jwt.encode(payload, os.environ['APP_KEY'] , algorithm='RS256')

        return jwt_auth

class appClient():
    """ Client object to wrap and contain necessary functions and variables
        to interact with the App.
    """
    def __init__(self):
        self._payload = None
        self.bearer_token = generate_jwt_token()
        self.installation_token = self.create_installation_app_token()

    @property
    def payload(self):
        """ The current payload of the client
        """
        return self._payload

    @payload.setter
    def payload(self, payload):
        self._payload = payload

    def create_check_run(self):
        """ Creates a check run through the API
        """
        logging.info('Creating check run...')
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
            'Authorization': self.installation_token,
            'Accept': 'application/vnd.github.antiope-preview+json',
        }
        params = {
            'name': 'RosiePi',
            'head_sha': head_sha,
        }
        response = requests.post(url, headers=header, params=params)

        return response.status_code

    def initiate_check_run(self):
        """ Initiates a previously created check run
        """
        logging.info('Initiating check run...')
        if not self.installation_token:
            logging.info(
                'Check run not initiated. No installation token available.'
            )
            return 401

        repo_name = self.payload['repository']['full_name']
        check_id = self.payload['check_run']['id']
        url = f'https://api.github.com/repos/{repo_name}/check-runs{check_id}'

        header = {
            'Authorization': self.installation_token,
            'Accept': 'application/vnd.github.antiope-preview+json',
        }
        params = {
            'name': 'RosiePi',
            'status': 'in_progress',
            'started_at': datetime.datetime.utcnow().isoformat()
        }
        response = requests.patch(url, headers=header, params=params)

        return response.status_code

    def create_installation_app_token(self):
        """ Retrieves a new app installation token to use with App/checks api
        """
        install_token = None
        if self.bearer_token:
            app_id = os.environ['APP_ID']
            url = f'https://api.github.com/app/installations/{app_id}/access_tokens'
            header = {
                'Authorization': self.bearer_token,
                'Accept': 'application/vnd.github.machine-man-preview+json'
            }
            response = requests.post(url, headers=header)
            if response.ok:
                install_token = response.json()['token']

        return install_token

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    
    logging.info('Header Info:')
    for item in req.headers:
        logging.info("\t{}: {}".format(item, req.headers[item]))

    event_status = 200

    if 'http-x-github-event' in req.headers:
        event_client = appClient()
        event = req.headers['http-x-github-event']
        payload = ""
        action = None
        try:
            payload = req.get_json()
            if payload:
                action = payload.get('action', None)
                event_client.payload = payload
        except ValueError:
            event = None
        
        if not event:
            event_status = 500        
        
        elif event == 'check_suite':
            logging.info(f'check_suite event: {event}')
            if action in ('requested', 'rerequested'):
                # create check_run
                event_status = event_client.create_check_run()
        
        elif event == 'check_run':
            if str(payload['check_run']['app']['id']) == os.environ['APP_ID']:
                if action == 'created':
                    # initiate check_run
                    event_status = event_client.initiate_check_run()
                elif action == 'rerequested':
                    # create check_run
                    event_status = event_client.create_check_run()


    logging.info(f'Event status: {event_status}')
    return func.HttpResponse(status_code=event_status)


    