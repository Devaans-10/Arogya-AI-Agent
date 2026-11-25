import os
import unittest
import json
from app import create_app
import database as db
import services.gemini_service as gemini

class NutritionAgentTestCase(unittest.TestCase):
    def setUp(self):
        # Override database to a separate test database
        self.db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_nutrition_agent.db')
        from config import Config
        Config.DATABASE = self.db_path
        
        # Re-initialize the test database schema
        db.init_db()
        
        # Force mock mode for Gemini services during testing
        gemini.use_mock = True
        
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()
        # Remove testing database
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_empty_profiles_redirects(self):
        """Verify redirect to /profiles if no family profile exists."""
        response = self.client.get('/', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/profiles' in response.location)

    def test_profile_page_loads(self):
        """Verify profiles manager page loads successfully."""
        response = self.client.get('/profiles')
        self.assertEqual(response.status_code, 200)

    def test_bmi_calculator_math(self):
        """Verify BMI calculation logic and output classifications."""
        payload = {'weight': 70, 'height': 175}
        response = self.client.post('/api/bmi/calculate', 
                                    data=json.dumps(payload), 
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['bmi'], 22.9)
        self.assertEqual(data['category'], 'Normal weight')

    def test_profile_crud_lifecycle(self):
        """Verify profile creation, targets calculation, updates, and deletion."""
        # 1. Create Profile
        payload = {
            'name': 'Test User',
            'age': 30,
            'gender': 'Male',
            'height_cm': 180,
            'weight_kg': 80,
            'activity_level': 'Sedentary',
            'diet_type': 'Vegetarian',
            'allergies': 'Peanuts'
        }
        response = self.client.post('/api/profiles',
                                    data=json.dumps(payload),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        profile_id = data['profile_id']

        # Verify profile is in db and macro calculations occurred (Mifflin BMR = 10*80 + 6.25*180 - 5*30 + 5 = 800+1125-150+5 = 1780. TDEE = 1780*1.2 = 2136)
        profile = db.get_profile(profile_id)
        self.assertIsNotNone(profile)
        self.assertEqual(profile['name'], 'Test User')
        self.assertEqual(profile['target_calories'], 2136)
        self.assertEqual(profile['target_protein'], 107) # (2136 * 0.20) / 4 = 106.8 -> 107
        
        # 2. Update Profile
        payload['weight_kg'] = 75
        response = self.client.post(f'/api/profiles/update/{profile_id}',
                                    data=json.dumps(payload),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        profile = db.get_profile(profile_id)
        self.assertEqual(profile['weight_kg'], 75)
        self.assertLess(profile['target_calories'], 2136) # Calorie budget should fall as weight decreases

        # 3. Delete Profile
        response = self.client.post(f'/api/profiles/delete/{profile_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(db.get_profile(profile_id))

    def test_mock_gemini_services(self):
        """Verify mock fallbacks for Gemini services operate properly."""
        profile_data = {
            'name': 'Aarav',
            'age': 25,
            'gender': 'Male',
            'height_cm': 170,
            'weight_kg': 65,
            'activity_level': 'Sedentary',
            'diet_type': 'Vegetarian',
            'allergies': ''
        }
        
        # Chat
        chat_resp = gemini.generate_nutrition_chat_response("What is healthy breakfast?", [], profile_data)
        self.assertIn("Aarav", chat_resp)
        self.assertIn("MOCK Mode", chat_resp)
        
        # Meal Planner
        plan = gemini.generate_meal_plan(profile_data, "Weight Loss", "daily")
        self.assertEqual(plan['target_calories'], 1800)
        self.assertTrue(len(plan['days']) == 1)
        self.assertEqual(plan['days'][0]['meals']['breakfast']['name'], "Poha with Roasted Peanuts & Sprouts")

        # Food analyzer
        analysis = gemini.analyze_food_input("I ate 2 rotis")
        self.assertEqual(analysis['calories'], 250)
        self.assertEqual(analysis['protein'], 8.0)

    def test_chat_quota_enforcement_and_402(self):
        """Verify chat quota enforcement: free limit hit returns 402 with upgrade_required."""
        from config import Config
        original_limit = Config.FREE_DAILY_CHAT_LIMIT
        Config.FREE_DAILY_CHAT_LIMIT = 2

        try:
            # Create a test profile
            profile_id = db.create_profile('Quota User', 28, 'Female', 165, 55, 'Sedentary', 'Vegetarian', '')
            
            # Message 1: allowed
            res1 = self.client.post('/api/chat', json={'profile_id': profile_id, 'message': 'Hello message 1'})
            self.assertEqual(res1.status_code, 200)
            data1 = json.loads(res1.data)
            self.assertTrue(data1['success'])
            self.assertEqual(data1['remaining_messages'], 1)
            self.assertFalse(data1['is_paid'])

            # Message 2: allowed (hits limit)
            res2 = self.client.post('/api/chat', json={'profile_id': profile_id, 'message': 'Hello message 2'})
            self.assertEqual(res2.status_code, 200)
            data2 = json.loads(res2.data)
            self.assertEqual(data2['remaining_messages'], 0)

            # Message 3: blocked with HTTP 402
            res3 = self.client.post('/api/chat', json={'profile_id': profile_id, 'message': 'Hello message 3'})
            self.assertEqual(res3.status_code, 402)
            data3 = json.loads(res3.data)
            self.assertEqual(data3['error'], 'upgrade_required')
            self.assertIn('Daily free chat limit reached', data3['message'])

            # Chat page renders the upgrade card when quota is exhausted
            page_res = self.client.get(f'/chat?profile_id={profile_id}')
            self.assertEqual(page_res.status_code, 200)
            self.assertIn(b'chatUpgradeCard', page_res.data)
            self.assertIn(b'Daily Free Chat Limit Reached', page_res.data)
        finally:
            Config.FREE_DAILY_CHAT_LIMIT = original_limit

    def test_paid_user_unlimited_chat(self):
        """Verify paid active subscribers have unlimited chat access with no quota blocks."""
        from config import Config
        original_limit = Config.FREE_DAILY_CHAT_LIMIT
        Config.FREE_DAILY_CHAT_LIMIT = 1

        try:
            profile_id = db.create_profile('Paid User', 32, 'Male', 175, 70, 'Lightly Active', 'Non-Vegetarian', '')
            
            # Activate subscription for the default owner
            db.upsert_subscription('default_owner', stripe_customer_id='cus_paid_test', stripe_subscription_id='sub_paid_test', status='active')

            # Send multiple messages exceeding free limit
            for i in range(3):
                res = self.client.post('/api/chat', json={'profile_id': profile_id, 'message': f'Paid message {i}'})
                self.assertEqual(res.status_code, 200)
                data = json.loads(res.data)
                self.assertTrue(data['success'])
                self.assertTrue(data['is_paid'])
                self.assertEqual(data['remaining_messages'], -1)
        finally:
            Config.FREE_DAILY_CHAT_LIMIT = original_limit

    def test_webhook_signature_rejection(self):
        """Verify invalid Stripe webhook signatures are rejected with HTTP 400."""
        from config import Config
        original_secret = Config.STRIPE_WEBHOOK_SECRET
        Config.STRIPE_WEBHOOK_SECRET = 'whsec_test_secret_abc123'

        try:
            payload = json.dumps({'id': 'evt_fake_123', 'type': 'checkout.session.completed'})
            res = self.client.post(
                '/webhooks/stripe',
                data=payload,
                headers={'Stripe-Signature': 't=123456,v1=invalid_signature_hash'}
            )
            self.assertEqual(res.status_code, 400)
            data = json.loads(res.data)
            self.assertIn('error', data)
        finally:
            Config.STRIPE_WEBHOOK_SECRET = original_secret

    def test_webhook_subscription_lifecycle_and_idempotency(self):
        """Verify subscription status updates from webhook events and event idempotency."""
        from unittest.mock import patch
        from config import Config
        original_secret = Config.STRIPE_WEBHOOK_SECRET
        Config.STRIPE_WEBHOOK_SECRET = 'whsec_test_secret_abc123'

        try:
            # 1. checkout.session.completed -> activates subscription
            checkout_evt = {
                'id': 'evt_checkout_success_1',
                'type': 'checkout.session.completed',
                'data': {
                    'object': {
                        'id': 'cs_test_999',
                        'customer': 'cus_sub_lifecycle',
                        'subscription': 'sub_lifecycle_001',
                        'client_reference_id': 'owner_lifecycle_test',
                        'metadata': {'owner_id': 'owner_lifecycle_test'}
                    }
                }
            }

            with patch('stripe.Webhook.construct_event', return_value=checkout_evt):
                res1 = self.client.post('/webhooks/stripe', data='raw_payload', headers={'Stripe-Signature': 'mock_sig'})
                self.assertEqual(res1.status_code, 200)
                data1 = json.loads(res1.data)
                self.assertEqual(data1['status'], 'success')

            # Verify subscription created in DB
            sub = db.get_owner_subscription('owner_lifecycle_test')
            self.assertEqual(sub['status'], 'active')
            self.assertEqual(sub['stripe_customer_id'], 'cus_sub_lifecycle')
            self.assertEqual(sub['stripe_subscription_id'], 'sub_lifecycle_001')

            # 2. Duplicate event -> idempotent, status already_processed
            with patch('stripe.Webhook.construct_event', return_value=checkout_evt):
                res_dup = self.client.post('/webhooks/stripe', data='raw_payload', headers={'Stripe-Signature': 'mock_sig'})
                self.assertEqual(res_dup.status_code, 200)
                data_dup = json.loads(res_dup.data)
                self.assertEqual(data_dup['status'], 'already_processed')

            # 3. customer.subscription.updated -> status change or period renewal
            sub_updated_evt = {
                'id': 'evt_sub_updated_2',
                'type': 'customer.subscription.updated',
                'data': {
                    'object': {
                        'id': 'sub_lifecycle_001',
                        'customer': 'cus_sub_lifecycle',
                        'status': 'active',
                        'current_period_end': 1999999999
                    }
                }
            }
            with patch('stripe.Webhook.construct_event', return_value=sub_updated_evt):
                res2 = self.client.post('/webhooks/stripe', data='raw_payload', headers={'Stripe-Signature': 'mock_sig'})
                self.assertEqual(res2.status_code, 200)

            # 4. invoice.payment_failed -> past_due
            invoice_failed_evt = {
                'id': 'evt_inv_failed_3',
                'type': 'invoice.payment_failed',
                'data': {
                    'object': {
                        'id': 'in_failed_001',
                        'customer': 'cus_sub_lifecycle',
                        'subscription': 'sub_lifecycle_001'
                    }
                }
            }
            with patch('stripe.Webhook.construct_event', return_value=invoice_failed_evt):
                res3 = self.client.post('/webhooks/stripe', data='raw_payload', headers={'Stripe-Signature': 'mock_sig'})
                self.assertEqual(res3.status_code, 200)

            sub_after_fail = db.get_owner_subscription('owner_lifecycle_test')
            self.assertEqual(sub_after_fail['status'], 'past_due')

            # 5. customer.subscription.deleted -> canceled
            sub_deleted_evt = {
                'id': 'evt_sub_deleted_4',
                'type': 'customer.subscription.deleted',
                'data': {
                    'object': {
                        'id': 'sub_lifecycle_001',
                        'customer': 'cus_sub_lifecycle',
                        'status': 'canceled'
                    }
                }
            }
            with patch('stripe.Webhook.construct_event', return_value=sub_deleted_evt):
                res4 = self.client.post('/webhooks/stripe', data='raw_payload', headers={'Stripe-Signature': 'mock_sig'})
                self.assertEqual(res4.status_code, 200)

            sub_after_del = db.get_owner_subscription('owner_lifecycle_test')
            self.assertEqual(sub_after_del['status'], 'canceled')

        finally:
            Config.STRIPE_WEBHOOK_SECRET = original_secret

    def test_pricing_page_and_medical_disclaimer(self):
        """Verify pricing page loads and displays educational disclaimer instead of medical advice."""
        res = self.client.get('/pricing')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Simple, Honest Pricing', res.data)
        self.assertIn(b'not a medical service', res.data)
        self.assertIn(b'not provide medical diagnoses', res.data)


if __name__ == '__main__':
    unittest.main()
