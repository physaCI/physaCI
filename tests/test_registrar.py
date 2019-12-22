
import json
import os
import requests
import unittest


class TestRegistrar(unittest.TestCase):
    def test_add_node(self):
        """ Test adding a node to the registrar.
        """

        payload = {'node_name': 'unittest_node'}
        url = (
            'https://physaci-app.azurewebsites.net/api/testnode-hook/'
            'registrar/add/?code={}'.format(os.environ['NODE_1_TOKEN'])
        )

        response = requests.post(url, json=payload)
        self.assertTrue(response.ok)

if __name__ == '__main__':
    unittest.main()