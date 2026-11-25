# AI-Powered Nutrition Agent 🌿

A full-stack, responsive web application built with **Python Flask** and **Google AI Gemini 1.5 Flash**. The application serves as a comprehensive family nutrition advisor featuring:

1. **Central Dashboard**: Tracking physical metrics, active family profiles, and custom Chart.js lines representing calorie intake histories.
2. **AI Natural Language Food Logger**: Instantly logs meals by parsing sentences (e.g. *"I ate 2 rotis, a cup of dal, and curd for lunch"*) into estimated calories and macronutrients using Gemini.
3. **AI Chat Assistant**: Provides conversational dietary suggestions, recipe instructions, local Indian food swaps, and sugar management.
4. **BMI & Health Calculator**: Visually charts your BMI on a colorful gauge pointer matching underweight, normal, overweight, and obese thresholds.
5. **Personalized Meal Planner**: Automatically constructs macro-balanced daily or weekly menus matching vegetarian, vegan, and non-vegetarian Indian food options.
6. **Family Profile Management**: Support for multiple profiles with automatic targets calculations (TDEE/BMR) customized to age, gender, and physical activity.
7. **Responsive UI**: Bootstrap 5 setup with smooth micro-animations and a persistent dark mode toggle.

---

## Project Structure

```
Nutrition AI AGENT/
├── .env                  # Created locally (contains API keys)
├── .env.example          # Template for environment variables
├── requirements.txt      # Python dependencies
├── config.py             # Config setup & AGENT_INSTRUCTIONS
├── database.py           # SQLite connection and helper CRUD routines
├── schema.sql            # Table structures for sqlite
├── app.py                # Main Flask entrypoint
├── test_app.py           # Integration test suite
├── routes/
│   ├── __init__.py
│   ├── main.py           # Webpages blueprint (HTML rendering)
│   └── api.py            # API blueprint (AJAX endpoints)
├── services/
│   ├── __init__.py
│   └── gemini_service.py # Google Generative AI integration
├── templates/
│   ├── base.html         # Master page layout (Navbar, CSS links)
│   ├── dashboard.html    # Charts, food tracker, dashboard
│   ├── chat.html         # Conversation view with quick prompts
│   ├── meal_planner.html # Plan generator & calendar grid
│   ├── bmi.html          # Interactive BMI calculator
│   └── profiles.html     # Add/Edit family profiles
└── static/
    ├── css/
    │   └── style.css     # Dark mode, glassmorphism layouts, animations
    └── js/
        └── app.js        # Form submissions, Chart updates, CSS slider
```

---

## Getting Started

### 1. Prerequisites
Make sure you have **Python 3.8+** installed on your system.

### 2. Local Installation & Setup
1. Clone or download this project folder.
2. Open your terminal in the project directory:
   ```bash
   cd "Nutrition AI AGENT"
   ```
3. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
4. Activate the virtual environment:
   - **Windows (CMD/PowerShell)**:
     ```powershell
     .\venv\Scripts\activate
     ```
   - **macOS/Linux**:
     ```bash
     source venv/bin/activate
     ```
5. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Gemini API Key Configuration
1. Obtain an API Key from [Google AI Studio](https://aistudio.google.com/).
2. Copy the `.env.example` file and rename it to `.env`:
   ```bash
   cp .env.example .env
   ```
3. Open `.env` and fill in your Gemini API Key:
   ```env
   GOOGLE_API_KEY=AIzaSyYourActualKeyHere
   ```
   > **Note**: If `GOOGLE_API_KEY` is not set or remains the placeholder value, the application will run in **Mock Mode**, providing pre-recorded responses and plan templates so you can test the UI immediately without hitting API quotas.

### 4. Running the Tests
Run the comprehensive unittest suite to verify the application:
```bash
python -m unittest test_app.py
```

### 5. Running the Application Locally
Launch the Flask development server:
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000/`.

---

## Customizing the AI Agent's Behavior

You can easily adjust the agent's tone, food suggestions, regional defaults, safety thresholds, and rules by editing the `AGENT_INSTRUCTIONS` constant in the **[config.py](file:///c:/Users/devaa/OneDrive/Desktop/Nutrition%20AI%20AGENT/config.py)** file.

Inside `config.py`, locate:
```python
AGENT_INSTRUCTIONS = """
You are an expert AI Nutrition Agent with a background in clinical dietetics...
...
"""
```
You can modify this system prompt to:
* **Add new safety rules**: E.g., *"If user mentions kidney disease, immediately block protein suggestions exceeding 0.8g/kg."*
* **Tailor regional styles**: Customize suggestions for specific states (Gujarati, Maharashtrian, Bengali, etc.).
* **Change Diet Specializations**: Direct the agent to lean towards keto, low-carb, high-protein, or intermittent fasting rules.

---

## 💳 Subscriptions & Gating System

The application includes a Stripe-powered subscription tier that gates the **AI Nutritionist Chat**:
- **Free Users**: Get `5` free AI chat messages per day (`FREE_DAILY_CHAT_LIMIT`). Dashboard, Food Logger, BMI Calculator, Meal Planner, and Profiles remain 100% free with no limits.
- **Pro Subscribers**: Get unlimited AI Nutritionist chat for the whole household account. Includes a Stripe Customer Portal to cancel or update payment methods anytime.
- **Server-Side Enforcement**: Quota and subscription checks are strictly verified on the server. When the quota is exceeded, `/api/chat` returns HTTP `402` with `{"error": "upgrade_required"}` and the UI dynamically displays an upgrade prompt.

### 1. Environment Variables

Add these to your `.env` file (see `.env.example`):
```env
# Daily free chat quota (default 5)
FREE_DAILY_CHAT_LIMIT=5

# Stripe API Keys (from https://dashboard.stripe.com/apikeys)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...

# Webhook signing secret (from Stripe CLI or Stripe Dashboard)
STRIPE_WEBHOOK_SECRET=whsec_...

# Recurring Subscription Price ID (from Stripe Products)
STRIPE_PRICE_ID=price_...

# Base URL for redirects (http://127.0.0.1:5000 locally or your Render domain in production)
APP_BASE_URL=http://127.0.0.1:5000
```

### 2. Testing Stripe Webhooks Locally

1. Install the [Stripe CLI](https://stripe.com/docs/stripe-cli).
2. Authenticate:
   ```bash
   stripe login
   ```
3. Start forwarding webhook events to your local Flask app:
   ```bash
   stripe listen --forward-to localhost:5000/webhooks/stripe
   ```
4. Copy the webhook signing secret printed by the CLI (`whsec_...`) into your `.env` as `STRIPE_WEBHOOK_SECRET`.
5. Trigger test events:
   ```bash
   stripe trigger checkout.session.completed
   stripe trigger customer.subscription.deleted
   stripe trigger invoice.payment_failed
   ```

### 3. Render Production Configuration

When deploying on [Render](https://dashboard.render.com):
1. In your Web Service settings, navigate to the **Environment** tab.
2. Add the following environment variables:
   - `FREE_DAILY_CHAT_LIMIT`: `5`
   - `STRIPE_SECRET_KEY`: `sk_live_...` (or `sk_test_...`)
   - `STRIPE_PUBLISHABLE_KEY`: `pk_live_...` (or `pk_test_...`)
   - `STRIPE_PRICE_ID`: `price_...`
   - `APP_BASE_URL`: `https://arogya-ai-agent.onrender.com`
   - `STRIPE_WEBHOOK_SECRET`: Webhook signing secret created from the Render endpoint below.
3. In your **Stripe Dashboard** -> **Developers** -> **Webhooks**:
   - Add endpoint URL: `https://arogya-ai-agent.onrender.com/webhooks/stripe`
   - Select events:
     - `checkout.session.completed`
     - `customer.subscription.created`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `invoice.payment_failed`
   - Copy the signing secret (`whsec_...`) into Render's `STRIPE_WEBHOOK_SECRET`.

---

## Deployment Instructions

### Option 1: Deploying on Render (Free Hosting)
1. Add `gunicorn` to your dependency checklist:
   ```bash
   pip install gunicorn
   ```
   and add `gunicorn==22.0.0` inside `requirements.txt`.
2. Create a Web Service on [Render](https://render.com/).
3. Connect your Git repository.
4. Set the following settings:
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app` (or automatically picked up from `Procfile`)
5. Go to **Environment** tab and add your keys:
   - `GOOGLE_API_KEY` = `your_gemini_api_key`
   - `SECRET_KEY` = `some_secure_random_hash`
   - `FREE_DAILY_CHAT_LIMIT` = `5`
   - `STRIPE_SECRET_KEY` = `sk_live_...`
   - `STRIPE_PUBLISHABLE_KEY` = `pk_live_...`
   - `STRIPE_WEBHOOK_SECRET` = `whsec_...`
   - `STRIPE_PRICE_ID` = `price_...`
   - `APP_BASE_URL` = `https://arogya-ai-agent.onrender.com`

### Option 2: Deploying on Google Cloud Run (Containerized)
1. Create a `Dockerfile` in the root folder:
   ```dockerfile
   FROM python:3.10-slim
   ENV PYTHONUNBUFFERED True
   ENV APP_HOME /app
   WORKDIR $APP_HOME
   COPY . ./
   RUN pip install --no-cache-dir -r requirements.txt gunicorn
   CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app
   ```
2. Build and publish your Docker container to Google Artifact Registry:
   ```bash
   gcloud builds submit --tag gcr.io/your-project-id/nutrition-agent
   ```
3. Deploy to Cloud Run:
   ```bash
   gcloud run deploy nutrition-agent \
     --image gcr.io/your-project-id/nutrition-agent \
     --platform managed \
     --allow-unauthenticated \
     --set-env-vars GOOGLE_API_KEY=your_gemini_key_here
   ```
