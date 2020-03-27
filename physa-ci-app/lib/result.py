import json
import logging
from azure.cosmosdb.table.models import Entity

REQUIRED_KEYS = {
    'node_name',
    'check_run_suite_id',
    'check_run_id',
    'check_run_head_sha',
    'check_run_url',
    'check_run_pull_requests',
    #'check_run_status',
    #'node_results',
    #'node_results_raw',
    #'check_run_conclusion',
    #'check_run_started_at',
    #'check_run_output',
    #'check_run_details_url',
}

class Result():
    """ Class containing a test result, supplied by a node.
    """

    def __init__(self, results):
        self.results = verify_results(results)

    def results_to_table_entity(self):
        """ Format the results into an Azure Storage Table entity.

        :return: azure.cosmodb.table.models.Entity or None
        """
        if self.results:
            temp_results = self.results
            entity = Entity()
            entity.PartitionKey = temp_results.pop('node_name')
            
            run_id = temp_results.pop('check_run_id')
            padding = '0'*(50 - len(run_id))
            padded_id = f'{padding}{run_id}'
            entity.RowKey = padded_id

            for key, value in temp_results.items():
                if isinstance(value, list):
                    value = ','.join(value)
                entity.update({key: value})

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

    if verified:
        diff = REQUIRED_KEYS.difference(verified.keys())
        if diff:
            logging.info(f'Failed to verify results. Missing data: {diff}')
            verified = None

    return verified
