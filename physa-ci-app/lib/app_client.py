import datetime
import logging
import os
import requests

import jwt

def generate_jwt_token():
        """ Authenticate with GitHub as an App so that we can
            process API requests
        """
        jwt_auth = None

        logging.info('Generating JWT...')

        utc_now = datetime.datetime.utcnow()
        secret = bytes(os.environ['GITHUB_APP_KEY'], encoding='utf-8')
        payload = {
            'iat': utc_now,
            'exp': utc_now + datetime.timedelta(minutes=5),
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