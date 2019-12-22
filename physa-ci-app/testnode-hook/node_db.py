import logging
import os

from azure.cosmosdb.table.tableservice import TableService
from azure.cosmosdb.table.models import Entity


def add_result(results_entity):
    """ Adds a new result to the ``rosiepi`` storage table.

    :param: results_entity: A ``azure.cosmodb.table.models.Entity`` object
                            containing the results to add to the storage
                            table. ``Entity`` object can be retrieved from
                            ``lib/result.py::Result.resultsToTableEntity()``.

    :return: The entity's Etag if successful. None if failed.
    """

    response = None
    if isinstance(results_entity, Entity):
        table = TableService(connection_string=os.environ['APP_STORAGE_CONN_STR'])

        try:
            response = table.insert_entity('rosiepi', results_entity)
        except Exception as err:
            logging.info(f'Failed to add result to rosiepi table. Error: {err}')
    else:
        logging.info(
            'Result not added to rosiepi table. Supplied result was an incorrect '
            'type. Should be azure.cosmodb.table.models.Entity. Supplied type: '
            f'{type(results_entity)}'
        )

    return response

def update_result(results_entity):
    """ Updates a result in the ``rosiepi`` storage table.

    :param: results_entity: A ``azure.cosmodb.table.models.Entity`` object
                            containing the results to add to the storage
                            table. ``Entity`` object can be retrieved from
                            ``lib/result.py::Result.resultsToTableEntity()``.

    :return: The entity's Etag if successful. None if failed.
    """

    response = None
    if isinstance(results_entity, Entity):
        table = TableService(connection_string=os.environ['APP_STORAGE_CONN_STR'])

        try:
            response = table.update_entity('rosiepi', results_entity)
        except Exception as err:
            logging.info(f'Failed to update result in rosiepi table. Error: {err}')
    else:
        logging.info(
            'Result not updated in rosiepi table. Supplied result was an incorrect '
            'type. Should be azure.cosmodb.table.models.Entity. Supplied type: '
            f'{type(results_entity)}'
        )

    return response
