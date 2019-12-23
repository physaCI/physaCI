
import json
import os
import requests
import time
import unittest


def node_request():
    payload = {'node_name': 'unittest_node'}
    url = (
        'https://physaci-app.azurewebsites.net/api/testnode-hook/'
        'registrar/add/?code={}'.format(os.environ['NODE_1_TOKEN'])
    )

    response = requests.post(url, json=payload)
    
    return response

class TestRegistrar(unittest.TestCase):
    def test_add_node(self):
        """ Test adding a node to the registrar.
        """

        response = node_request()
        self.assertTrue(response.ok)

    def test_add_when_node_exists(self):
        """ Test adding a node when it already exists in the registrar.
            Relies on test_add_node success...
        """

        # wait 1 second to ensure queue visibility
        time.sleep(1)
        response = node_request()
        self.assertTrue(response.ok)


if __name__ == '__main__':
    unittest.main()