import json
import logging
import os

from azure.cosmosdb.table.tableservice import TableService
from azure.cosmosdb.table.models import Entity

IGNORED_ITEMS = [
    # Timestamps are returned as datetime objects and are not JSONable.
    # Further, they are ignored when sent to a Table, so we can just
    # drop them.
    'Timestamp',
    # etags are not used for cache/compare, so don't pollute the
    # tables with them.
    'etag',
]

def get_result(partition_key, row_key, tbl_svc_retry=None, **kwargs):
    """ Retirieves a result from the ``rosiepi`` storage table.

    :param: partition_key: The ``PartitionKey`` of the entity
    :param: row_key: The ``RowKey`` of the entity
    :param: **kwargs: Any additional kwargs to pass onto the
                      ``TableService.get_entity()`` function.

    :return: The ``TableService.Entity``, or None if the Entity
             isn't found.
    """

    response = None

    table = TableService(connection_string=os.environ['APP_STORAGE_CONN_STR'])
    if tbl_svc_retry is not None:
        table.retry = tbl_svc_retry

    # ensure RowKey is properly padded
    padding = '0'*(50 - len(row_key))
    row_key = f'{padding}{row_key}'

    try:
        response = table.get_entity('rosiepi', partition_key, row_key, **kwargs)
    except Exception as err:
        logging.info(f'Failed to get result from rosiepi table. Error: {err}')
        raise

    logging.info(f'TableService.Entity retrieved: {response}')

    # Flatten the entity
    json_data_copy = response.get('json_data')
    if json_data_copy:
        del response['json_data']
        try:
            flat_data = json.loads(json_data_copy)
            response.update(flat_data)
        except Exception as err:
            logging.info('Failed to flatten TableService.Entity.')
            raise

    for item in IGNORED_ITEMS:
        if item in response:
            del response[item]
    
    return response

def add_result(results_entity):
    """ Adds a new result to the ``rosiepi`` storage table.

    :param: results_entity: A ``azure.cosmodb.table.models.Entity`` object
                            containing the results to add to the storage
                            table. ``Entity`` object can be retrieved from
                            ``lib/result.py::Result.results_to_table_entity()``.

    :return: The entity's Etag if successful. None if failed.
    """

    response = None
    if isinstance(results_entity, Entity):
        table = TableService(connection_string=os.environ['APP_STORAGE_CONN_STR'])

        try:
            response = table.insert_entity('rosiepi', results_entity)
        except Exception as err:
            logging.info(f'Failed to add result to rosiepi table. Error: {err}\nEntity: {results_entity}')
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
                            ``lib/result.py::Result.results_to_table_entity()``.

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
