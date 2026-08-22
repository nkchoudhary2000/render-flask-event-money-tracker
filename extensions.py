from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_cors import CORS
from flasgger import Swagger
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
cors = CORS()
swagger = Swagger()
migrate = Migrate()

# Configure Flask-Login defaults
login_manager.login_view = "ui.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"
