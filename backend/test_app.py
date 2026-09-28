import json
import hashlib
import hmac
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, 'backend')
TEST_DATABASE_PATH = os.path.join(
	tempfile.gettempdir(),
	'rakjid_datahub_test.sqlite3',
)
os.environ['DATAHUB_DATABASE_PATH'] = TEST_DATABASE_PATH
os.environ['AUTH_TOKEN_SECRET'] = 'test-only-auth-secret'
os.environ['SME_API_BASE_URL'] = ''
os.environ['SME_API_KEY'] = ''
os.environ['PAYSTACK_SECRET_KEY'] = ''
os.environ['PUBLIC_API_URL'] = ''
if os.path.exists(TEST_DATABASE_PATH):
	os.remove(TEST_DATABASE_PATH)

from app import app


class AppBehaviorTests(unittest.TestCase):
	def setUp(self):
		self.client = app.test_client()

	def signup(self, name, email):
		response = self.client.post(
			'/api/auth/signup',
			json={'name': name, 'email': email, 'password': 'secret123'},
		)
		return response.get_json()

	def auth_headers(self, name, email):
		payload = self.signup(name, email)
		return {'Authorization': f"Bearer {payload['access_token']}"}

	def test_health_endpoint(self):
		response = self.client.get('/api/health')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.get_json()['status'], 'ok')

	def test_root_endpoint_identifies_api(self):
		response = self.client.get('/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.get_json()['status'], 'ok')

	def test_purchase_endpoint_accepts_valid_request(self):
		headers = self.auth_headers('Purchase User', 'purchase@example.com')
		response = self.client.post(
			'/api/purchase',
			headers=headers,
			json={
				'plan_id': 'mtn-1gb',
				'phone': '08031234567',
				'network': 'MTN',
			},
		)
		self.assertEqual(response.status_code, 503)

	def test_wallet_and_transactions_are_available(self):
		headers = self.auth_headers('Wallet User', 'wallet@example.com')
		wallet_response = self.client.get('/api/wallet', headers=headers)
		self.assertEqual(wallet_response.status_code, 200)
		self.assertIn('balance', wallet_response.get_json())

		history_response = self.client.get('/api/transactions', headers=headers)
		self.assertEqual(history_response.status_code, 200)
		self.assertIn('transactions', history_response.get_json())

	def test_airtime_purchase_endpoint(self):
		headers = self.auth_headers('Airtime User', 'airtime@example.com')
		response = self.client.post(
			'/api/airtime',
			headers=headers,
			json={
				'phone': '08031234568',
				'network': 'MTN',
				'amount': 500,
			},
		)
		self.assertEqual(response.status_code, 402)

	def test_wallet_topup_endpoint(self):
		headers = self.auth_headers('Topup User', 'topup@example.com')
		init_response = Mock()
		init_response.json.return_value = {
			'status': True,
			'data': {'authorization_url': 'https://checkout.paystack.com/example'},
		}
		verify_response = Mock()
		with patch.dict(os.environ, {
			'PAYSTACK_SECRET_KEY': 'test-paystack-secret',
			'PUBLIC_API_URL': 'https://api.example.com',
		}), patch('app.requests.post', return_value=init_response) as initialize, patch(
			'app.requests.get'
		) as verify:
			response = self.client.post(
				'/api/wallet/topup',
				headers=headers,
				json={'amount': 1500},
			)
			self.assertEqual(response.status_code, 201)
			payload = response.get_json()['data']
			reference = payload['reference']
			verify_response.json.return_value = {
				'status': True,
				'data': {
					'status': 'success',
					'reference': reference,
					'amount': 150000,
					'currency': 'NGN',
				},
			}
			self.assertEqual(initialize.call_args.kwargs['json']['amount'], 150000)
			self.assertEqual(
				self.client.get('/api/wallet', headers=headers).get_json()['balance'],
				0,
			)

			verify.return_value = verify_response
			verify_payload = {'reference': reference}
			first = self.client.post(
				'/api/wallet/topup/verify', headers=headers, json=verify_payload,
			)
			second = self.client.post(
				'/api/wallet/topup/verify', headers=headers, json=verify_payload,
			)

		self.assertEqual(first.status_code, 200)
		self.assertEqual(second.status_code, 200)
		self.assertEqual(first.get_json()['balance'], 1500)
		self.assertEqual(second.get_json()['balance'], 1500)
		self.assertEqual(verify.call_count, 1)
		history = self.client.get('/api/transactions', headers=headers).get_json()
		self.assertEqual(len(history['transactions']), 1)

	def test_paystack_webhook_requires_valid_signature(self):
		headers = self.auth_headers('Webhook User', 'webhook@example.com')
		with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': 'test-paystack-secret'}):
			response = self.client.post(
				'/api/payments/paystack/webhook',
				data=b'{"event":"charge.success"}',
				headers={'x-paystack-signature': 'invalid'},
			)
		self.assertEqual(response.status_code, 401)

	def test_signed_paystack_webhook_credits_once(self):
		headers = self.auth_headers('Signed Webhook User', 'signed-webhook@example.com')
		secret = 'test-paystack-secret'
		init_response = Mock()
		init_response.json.return_value = {
			'status': True,
			'data': {'authorization_url': 'https://checkout.paystack.com/example'},
		}
		with patch.dict(os.environ, {
			'PAYSTACK_SECRET_KEY': secret,
			'PUBLIC_API_URL': 'https://api.example.com',
		}), patch('app.requests.post', return_value=init_response):
			init = self.client.post(
				'/api/wallet/topup', headers=headers, json={'amount': 900},
			)

		reference = init.get_json()['data']['reference']
		body = json.dumps({
			'event': 'charge.success',
			'data': {
				'reference': reference,
				'status': 'success',
				'amount': 90000,
				'currency': 'NGN',
			},
		}).encode()
		signature = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
		with patch.dict(os.environ, {'PAYSTACK_SECRET_KEY': secret}):
			first = self.client.post(
				'/api/payments/paystack/webhook',
				data=body,
				headers={'Content-Type': 'application/json', 'x-paystack-signature': signature},
			)
			second = self.client.post(
				'/api/payments/paystack/webhook',
				data=body,
				headers={'Content-Type': 'application/json', 'x-paystack-signature': signature},
			)

		self.assertEqual(first.status_code, 200)
		self.assertEqual(second.status_code, 200)
		self.assertEqual(
			self.client.get('/api/wallet', headers=headers).get_json()['balance'],
			900,
		)
		transactions = self.client.get('/api/transactions', headers=headers).get_json()
		self.assertEqual(len(transactions['transactions']), 1)

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
		self.assertTrue(payload['access_token'])

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
		self.assertTrue(payload['access_token'])

	def test_password_reset_token_changes_password_once(self):
		self.signup('Reset User', 'reset@example.com')
		smtp_settings = {
			'SMTP_HOST': 'smtp.example.com',
			'SMTP_FROM_EMAIL': 'support@example.com',
			'PUBLIC_API_URL': 'https://api.example.com',
		}
		with patch.dict(os.environ, smtp_settings), patch(
			'app.send_password_reset_email'
		) as send_email:
			request_response = self.client.post(
				'/api/auth/forgot-password',
				json={'email': 'reset@example.com'},
			)
			self.assertEqual(request_response.status_code, 200)
			token = send_email.call_args.args[1]

		reset_response = self.client.post(
			'/api/auth/reset-password',
			json={'token': token, 'password': 'new-secret-123'},
		)
		self.assertEqual(reset_response.status_code, 200)

		replay_response = self.client.post(
			'/api/auth/reset-password',
			json={'token': token, 'password': 'another-secret-123'},
		)
		self.assertEqual(replay_response.status_code, 400)
		login_response = self.client.post(
			'/api/auth/login',
			json={'email': 'reset@example.com', 'password': 'new-secret-123'},
		)
		self.assertEqual(login_response.status_code, 200)

	def test_password_reset_page_requires_token(self):
		response = self.client.get('/reset-password')
		self.assertEqual(response.status_code, 400)

	def test_wallet_and_transactions_are_isolated_by_user(self):
		first_headers = self.auth_headers('First User', 'first-wallet@example.com')
		second_headers = self.auth_headers('Second User', 'second-wallet@example.com')
		topup_response = self.client.post(
			'/api/wallet/topup',
			json={'amount': 1200},
			headers=first_headers,
		)

		self.assertEqual(topup_response.status_code, 503)
		first_wallet = self.client.get('/api/wallet', headers=first_headers).get_json()
		second_wallet = self.client.get('/api/wallet', headers=second_headers).get_json()
		first_history = self.client.get(
			'/api/transactions', headers=first_headers
		).get_json()['transactions']
		second_history = self.client.get(
			'/api/transactions', headers=second_headers
		).get_json()['transactions']

		self.assertEqual(topup_response.status_code, 503)
		self.assertEqual(first_wallet['balance'], 0)
		self.assertEqual(second_wallet['balance'], 0)
		self.assertEqual(first_history, [])
		self.assertEqual(second_history, [])

	def test_protected_endpoints_reject_missing_or_forged_identity(self):
		response = self.client.get(
			'/api/wallet',
			headers={'X-User-Id': 'user_someone-elses-id'},
		)
		self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
	unittest.main()
