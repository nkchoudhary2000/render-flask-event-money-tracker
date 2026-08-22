import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app import create_app

# Create application for Gunicorn WSGI server
env_name = os.getenv("FLASK_ENV", "production")
app = create_app(config_name=env_name)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
