# StartBet Verification Bot

This is a Telegram bot designed to verify user registrations and deposits on the StartBet platform before granting access to an exclusive app and signal group.

## Features

1.  **Welcome & Verification**: Asks users if they want access to the app.
2.  **Registration Check**: Requires a screenshot of the StartBet account logged in with a 0.00 balance.
3.  **Deposit Check**: Requires a screenshot of the StartBet account with a positive balance (minimum R$ 20.00).
4.  **Automatic Reminders**:
    *   Sends a warning after 2 minutes if the user hasn't responded to the initial greeting.
    *   Sends a group link reminder after 5 minutes if the user hasn't sent the registration print.
5.  **Image Analysis**: Uses Google Gemini AI to analyze screenshots and verify account status and balances.

## Setup

1.  Clone the repository.
2.  Install dependencies: `pip install -r requirements.txt`
3.  Create a `.env` file with your keys:
    ```
    TELEGRAM_TOKEN=your_telegram_bot_token
    GEMINI_API_KEY=your_gemini_api_key
    ```
4.  Run the bot: `python main.py`

## Deployment (Railway)

The project includes a `Procfile` for easy deployment on platforms like Railway or Heroku.

*   **Build Command**: `pip install -r requirements.txt`
*   **Start Command**: `python main.py`
