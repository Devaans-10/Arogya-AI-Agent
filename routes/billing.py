import stripe
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
from config import Config
import database as db

billing_bp = Blueprint('billing', __name__)

def get_current_owner_id():
    """
    Returns the account/owner identifier.
    In this household/multi-profile application, all profiles belong
    to the active owner/household account.
    We check request headers/params first, then session['owner_id'],
    defaulting to 'default_owner' if not set.
    """
    owner = request.headers.get('X-Owner-Id') or request.args.get('owner_id')
    if owner:
        return owner
    if 'owner_id' not in session:
        session['owner_id'] = 'default_owner'
    return session['owner_id']

@billing_bp.route('/pricing', methods=['GET'])
def pricing_page():
    owner_id = get_current_owner_id()
    subscription = db.get_owner_subscription(owner_id)
    is_paid = db.is_subscription_active(owner_id)
    free_limit = Config.FREE_DAILY_CHAT_LIMIT
    daily_usage = db.get_daily_chat_usage(owner_id)
    remaining_messages = max(0, free_limit - daily_usage) if not is_paid else -1

    return render_template(
        'pricing.html',
        owner_id=owner_id,
        subscription=subscription,
        is_paid=is_paid,
        free_limit=free_limit,
        daily_usage=daily_usage,
        remaining_messages=remaining_messages,
        stripe_publishable_key=Config.STRIPE_PUBLISHABLE_KEY,
        stripe_price_id=Config.STRIPE_PRICE_ID
    )

@billing_bp.route('/subscribe/checkout', methods=['POST'])
def create_checkout_session():
    if not Config.STRIPE_SECRET_KEY or not Config.STRIPE_PRICE_ID:
        flash("Stripe billing is not configured yet. Please check your environment variables.", "warning")
        return redirect(url_for('billing.pricing_page'))

    stripe.api_key = Config.STRIPE_SECRET_KEY
    owner_id = get_current_owner_id()
    subscription = db.get_owner_subscription(owner_id)

    checkout_kwargs = {
        'mode': 'subscription',
        'payment_method_types': ['card'],
        'line_items': [{
            'price': Config.STRIPE_PRICE_ID,
            'quantity': 1,
        }],
        'client_reference_id': owner_id,
        'metadata': {'owner_id': owner_id},
        'subscription_data': {'metadata': {'owner_id': owner_id}},
        'success_url': f"{Config.APP_BASE_URL.rstrip('/')}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
        'cancel_url': f"{Config.APP_BASE_URL.rstrip('/')}/subscribe/cancel",
    }

    # Re-use existing customer ID if already established
    if subscription.get('stripe_customer_id'):
        checkout_kwargs['customer'] = subscription['stripe_customer_id']

    try:
        checkout_session = stripe.checkout.Session.create(**checkout_kwargs)
        if request.is_json:
            return jsonify({'success': True, 'checkout_url': checkout_session.url})
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f"Error starting checkout: {str(e)}", "danger")
        return redirect(url_for('billing.pricing_page'))

@billing_bp.route('/subscribe/success', methods=['GET'])
def subscribe_success():
    session_id = request.args.get('session_id')
    owner_id = get_current_owner_id()

    if session_id and Config.STRIPE_SECRET_KEY:
        try:
            stripe.api_key = Config.STRIPE_SECRET_KEY
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            customer_id = checkout_session.get('customer')
            sub_id = checkout_session.get('subscription')
            ref_owner = checkout_session.get('client_reference_id') or checkout_session.get('metadata', {}).get('owner_id') or owner_id
            
            db.upsert_subscription(
                owner_id=ref_owner,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                status='active'
            )
        except Exception as e:
            # Webhook will be the authoritative source if retrieve fails
            pass

    flash("🎉 Welcome to Pro! You now have unlimited AI Nutritionist chat across all family profiles.", "success")
    return redirect(url_for('main.chat_page'))

@billing_bp.route('/subscribe/cancel', methods=['GET'])
def subscribe_cancel():
    flash("Subscription checkout was cancelled. You can continue with your daily free chats.", "info")
    return redirect(url_for('billing.pricing_page'))

@billing_bp.route('/billing/portal', methods=['POST'])
def create_customer_portal():
    if not Config.STRIPE_SECRET_KEY:
        flash("Stripe billing is not configured yet.", "warning")
        return redirect(url_for('billing.pricing_page'))

    owner_id = get_current_owner_id()
    subscription = db.get_owner_subscription(owner_id)

    customer_id = subscription.get('stripe_customer_id')
    if not customer_id:
        flash("No active billing account found. Please subscribe to Pro first.", "warning")
        return redirect(url_for('billing.pricing_page'))

    try:
        stripe.api_key = Config.STRIPE_SECRET_KEY
        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{Config.APP_BASE_URL.rstrip('/')}/pricing"
        )
        if request.is_json:
            return jsonify({'success': True, 'portal_url': portal_session.url})
        return redirect(portal_session.url, code=303)
    except Exception as e:
        flash(f"Error accessing customer portal: {str(e)}", "danger")
        return redirect(url_for('billing.pricing_page'))

@billing_bp.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    if not Config.STRIPE_WEBHOOK_SECRET:
        return jsonify({'error': 'Stripe webhook secret not configured'}), 500

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, Config.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        return jsonify({'error': 'Invalid signature'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    event_id = event.get('id')
    event_type = event.get('type')

    # Idempotency check: Ignore duplicate events
    if db.is_event_processed(event_id):
        return jsonify({'status': 'already_processed', 'event_id': event_id}), 200

    # Event dispatching
    if event_type == 'checkout.session.completed':
        session_obj = event['data']['object']
        customer_id = session_obj.get('customer')
        sub_id = session_obj.get('subscription')
        owner_id = session_obj.get('client_reference_id') or session_obj.get('metadata', {}).get('owner_id')

        if owner_id:
            db.upsert_subscription(
                owner_id=owner_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                status='active'
            )
        elif customer_id:
            db.update_subscription_status(
                status='active',
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id
            )

    elif event_type in ('customer.subscription.created', 'customer.subscription.updated'):
        sub_obj = event['data']['object']
        sub_id = sub_obj.get('id')
        customer_id = sub_obj.get('customer')
        status = sub_obj.get('status')
        current_period_end = sub_obj.get('current_period_end')
        owner_id = sub_obj.get('metadata', {}).get('owner_id')

        if owner_id:
            db.upsert_subscription(
                owner_id=owner_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                status=status,
                current_period_end=current_period_end
            )
        else:
            db.update_subscription_status(
                status=status,
                stripe_subscription_id=sub_id,
                stripe_customer_id=customer_id,
                current_period_end=current_period_end
            )

    elif event_type == 'customer.subscription.deleted':
        sub_obj = event['data']['object']
        sub_id = sub_obj.get('id')
        customer_id = sub_obj.get('customer')
        db.update_subscription_status(
            status='canceled',
            stripe_subscription_id=sub_id,
            stripe_customer_id=customer_id
        )

    elif event_type == 'invoice.payment_failed':
        invoice_obj = event['data']['object']
        customer_id = invoice_obj.get('customer')
        sub_id = invoice_obj.get('subscription')
        db.update_subscription_status(
            status='past_due',
            stripe_subscription_id=sub_id,
            stripe_customer_id=customer_id
        )

    # Record event in db for idempotency
    db.record_processed_event(event_id, event_type)

    return jsonify({'status': 'success', 'event_id': event_id}), 200
