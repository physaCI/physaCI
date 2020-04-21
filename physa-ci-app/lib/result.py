import copy
import json
import logging
import re
from azure.cosmosdb.table.models import Entity


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
            temp_results = copy.deepcopy(self.results)
            entity = Entity()
            entity.PartitionKey = temp_results.get('node_name')
            
            run_id = temp_results.get('check_run_id')
            padding = '0'*(50 - len(run_id))
            padded_id = f'{padding}{run_id}'
            entity.RowKey = padded_id
 
            for item in ('PartitionKey', 'RowKey'):
                if item in temp_results:
                    del temp_results[item]

            try:
                json_data = json.dumps(temp_results)
                entity.update({'json_data': json_data})
            except json.JSONDecodeError:
                logging.warning(
                    'Failed to JSONify results_to_table_entity value. '
                    f'Original value: {temp_results}'
                )
                raise

            return entity

    def results_to_github(self, key_prefix='check_run_'):
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

    return verified
