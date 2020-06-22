import logging
import json
import pathlib

import azure.functions as func
from azure.core.exceptions import AzureError
from azure.common import AzureHttpError
from azure.cosmosdb.table.common import no_retry

# pylint: disable=import-error
from __app__.lib import node_db


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    response_kwargs = {
        'status_code': 200,
        'body': {},
        'headers': {
            'Content-Type': 'application/json'
        },
    }

    partition_key = req.params.get('node')
    row_key = req.params.get('job-id')

    logging.info(f'partition_key: {partition_key} | row_key: {row_key}')
    
    if partition_key and row_key:
        job_data = None
        try:
            job_data = node_db.get_result(partition_key, row_key, tbl_svc_retry=no_retry)
        except (AzureError, AzureHttpError) as err:
            logging.info(f"AzureError caught: {err}")
            pass

        logging.info(f'node_db result: {job_data}')
        
        if job_data:
            github_commit_sha = job_data.get('check_run_head_sha')
            check_run_url = job_data.get('check_run_url')
            check_run_date = job_data.get('check_run_completed_at', 'Unknown')
            outcome = job_data.get('check_run_conclusion')
            node_name = job_data.get('node_name', 'Unknown')
            node_results = job_data.get('node_results')

            response_kwargs['body'] = {
                'commit_sha': github_commit_sha,
                'check_run_url': check_run_url,
                'check_run_date': check_run_date,
                'outcome': outcome,
                'node_name': node_name,
                'node_results': node_results
            }
        
        else:
            logging.warning('Failed to retrieve job info.')

            failure_body = {
                'failure_reason': 'RosiePi Job match not found.'
            }

            response_kwargs.update(
                status_code=404,
                body=failure_body
            )

    else:
        logging.warning('Request missing required parameters.')

        failure_body = {
            'failure_reason': 'Missing required paramaters.'
        }

        response_kwargs.update(
            status_code=400,
            body=failure_body
        )

    try:
        response_kwargs['body'] = json.dumps(response_kwargs['body'])
    
    except json.JSONDecodeError as err:
        logging.error(f'Failed to JSON encode return message: {err}')
        logging.error(f'Attempted to encode the following: {response_kwargs["body"]}')
        response_kwargs.update(
            body='Internal Server Error.',
            status_code=500,
            headers={}
        )


    return func.HttpResponse(**response_kwargs)
