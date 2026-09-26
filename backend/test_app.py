import unittest
import sys
import os
import tempfile

sys.path.insert(0, 'backend')
TEST_DATABASE_PATH = os.path.join(
    tempfile.gettempdir(),
    'rakjid_datahub_test.sqlite3',
)
os.environ['DATAHUB_DATABASE_PATH'] = TEST_DATABASE_PATH
if os.path.exists(TEST_DATABASE_PATH):
    os.remove(TEST_DATABASE_PATH)

from app import app


class AppBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health_endpoint(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['status'], 'ok')

    def test_purchase_endpoint_accepts_valid_request(self):
        response = self.client.post(
            '/api/purchase',
            json={
                'plan_id': 'mtn-1gb',
                'phone': '08031234567',
                'network': 'MTN',
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn('success', payload)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['network'], 'MTN')

    def test_wallet_and_transactions_are_available(self):
        wallet_response = self.client.get('/api/wallet')
        self.assertEqual(wallet_response.status_code, 200)
        self.assertIn('balance', wallet_response.get_json())

        history_response = self.client.get('/api/transactions')
        self.assertEqual(history_response.status_code, 200)
        self.assertIn('transactions', history_response.get_json())

    def test_airtime_purchase_endpoint(self):
        response = self.client.post(
            '/api/airtime',
            json={
                'phone': '08031234568',
                'network': 'MTN',
                'amount': 500,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['data']['network'], 'MTN')

    def test_wallet_topup_endpoint(self):
        response = self.client.post(
            '/api/wallet/topup',
            json={'amount': 1500},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertGreater(payload['data']['balance'], 5000)

    def test_signup_endpoint_creates_account(self):
        response = self.client.post(
            '/api/auth/signup',
            json={
                'name': 'Jane Doe',
                'email': 'jane@example.com',
                'password': 'secret123',
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['user']['email'], 'jane@example.com')

    def test_login_endpoint_accepts_registered_user(self):
        self.client.post(
            '/api/auth/signup',
            json={
                'name': 'John Doe',
                'email': 'john@example.com',
                'password': 'demo456',
            },
        )

        response = self.client.post(
            '/api/auth/login',
            json={
                'email': 'john@example.com',
                'password': 'demo456',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['user']['email'], 'john@example.com')

    def test_wallet_and_transactions_are_isolated_by_user(self):
        first_user = self.client.post(
            '/api/auth/signup',
            json={
                'name': 'First User',
                'email': 'first-wallet@example.com',
                'password': 'secret123',
            },
        ).get_json()['user']
        second_user = self.client.post(
            '/api/auth/signup',
            json={
                'name': 'Second User',
                'email': 'second-wallet@example.com',
                'password': 'secret123',
            },
        ).get_json()['user']

        first_headers = {'X-User-Id': first_user['id']}
        second_headers = {'X-User-Id': second_user['id']}
        topup_response = self.client.post(
            '/api/wallet/topup',
            json={'amount': 1200},
            headers=first_headers,
        )

        self.assertEqual(topup_response.status_code, 200)
        first_wallet = self.client.get('/api/wallet', headers=first_headers).get_json()
        second_wallet = self.client.get('/api/wallet', headers=second_headers).get_json()
        first_history = self.client.get(
            '/api/transactions', headers=first_headers
        ).get_json()['transactions']
        second_history = self.client.get(
            '/api/transactions', headers=second_headers
        ).get_json()['transactions']

        self.assertEqual(first_wallet['balance'], 6200)
        self.assertEqual(second_wallet['balance'], 5000)
        self.assertEqual(len(first_history), 1)
        self.assertEqual(second_history, [])


if __name__ == '__main__':
    unittest.main()
