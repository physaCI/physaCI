import json
import logging
import requests

from datetime import datetime

import azure.functions as func

# pylint: disable=import-error
from __app__.lib import app_client, result, node_registrar, node_db

class QueueGithubClient(app_client.AppClient):
    """ Client object to wrap and contain necessary functions and variables
        to interact with the App.
    """
    def __init__(self):
        super().__init__()

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


def main(msg: func.QueueMessage) -> None:
    logging.info('Python queue trigger function processed a queue item: %s',
                 msg.get_body().decode('utf-8'))

    message = msg.get_body().decode()
    logging.info(f'Message is: {message}')
    
    check_info = json.loads(message)

    event_client = QueueGithubClient()
    event_client.payload = check_info
    github_output_summary = ''
    github_check_message = {}

    push_msg = json.dumps({
        'commit_sha': check_info['check_run_head_sha'],
        'check_run_id': check_info['check_run_id'],
    })

    push_result, node_name = node_registrar.push_test_to_nodes(push_msg)
    
    if push_result:
        check_info['node_name'] = node_name
        
        new_check = result.Result(check_info)
        if new_check.results:
            add_to_table = node_db.add_result(
                new_check.results_to_table_entity()
            )
            if not add_to_table:
                logging.info(
                    'Failed to add new check_run to table storage. '
                    f'Results Entity: {new_check.results_to_table_entity()}'
                )

        github_output_summary = (
            'RosiePi job has been queued on the following node: '
            f'{check_info["node_name"]}'
        )
        github_check_message = {
            'status': 'queued',
            'output': {
                'title': 'RosiePi',
                'summary': github_output_summary,
            }
        }

    else:
        logging.info('Job not accepted by a node, or push failed.')
        github_output_summary = 'Job not accepted by any RosiePi nodes.'
        github_check_message = {
            'status': 'completed',
            'conclusion': 'neutral',
            'completed_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'output': {
                'title': 'RosiePi',
                'summary': github_output_summary
            },
        }

    event_client.update_check_run(github_check_message)