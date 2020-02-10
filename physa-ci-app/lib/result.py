import json
import logging
from azure.cosmosdb.table.models import Entity

class Result():
    """ Class containing a test result, supplied by a node.
    """

    def __init__(self, results):
        self.results = verify_results(results)

    def results_to_table_entity(self):
        """ Format the results into an Azure Storage Table entity.

        :return: azure.cosmodb.table.models.Entity
        """
        if self.results:
            entity = Entity()
            entity.PartitionKey = self.results.pop('node_name')
            entity.RowKey = self.results['check_run_id']
            entity.update(self.results)

            return entity

    def results_to_github(self, key_prefix='check_run'):
        """ Format the results into a GitHub Check JSON message.

        :return: JSON string
        """
        if self.results:
            check_msg = None
            check_dict = {}
            for key, value in self.results.items():
                if (key.startswith(key_prefix) and not key.endswith('id')):
                    new_key = key.replace(key_prefix, '')
                    check_dict[new_key] = value

            try:
                check_msg = json.dumps(check_dict)
            except Exception as err:
                logging.info(
                    'Failed to translate results to GitHub Check format. '
                    'Malformed dict/JSON.\n'
                    f'Supplied dict: {check_dict}\n'
                    f'Error: {err}'
                )

            return check_msg


def verify_results(results):
    """ Verify supplied results to ensure proper format.

    :param: str,dict results: A JSON string or dict of the results.

    :return: dict
    """

    verified = None

    if isinstance(results, dict):
        verified = results
    elif isinstance(results, str):
        try:
            verified = json.loads(results)
        except Exception as err:
            logging.info(
                'Failed to verify results. Malformed JSON.\n'
                f'Supplied JSON string: {results}\n'
                f'Error: {err}'
            )
    else:
        logging.info(
                'Failed to verify results. Incorrect datatype '
                f'({type(results)}). Supplied results: {results}'
            )

    required_keys = {
        'node_name',
        'node_results',
        'node_results_raw',
        'check_run_suite_id',
        'check_run_id',
        'check_run_head_sha',
        'check_run_url',
        'check_run_pull_request',
        'check_run_status',
        'check_run_conclusion',
        'check_run_started_at',
        'check_run_output',
    }

    if verified:
        diff = required_keys.difference(verified.keys())
        if diff:
            logging.info(f'Failed to verify results. Missing data: {diff}')
            verified = None

    return verified
