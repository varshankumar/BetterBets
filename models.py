from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
from datetime import datetime

class User(UserMixin):
    def __init__(self, user_data):
        self.user_data = user_data if user_data else {}

    def get_id(self):
        return str(self.user_data.get('_id', None))

    def is_authenticated(self):
        return bool(self.user_data)

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    @property
    def id(self):
        return str(self.user_data.get('_id', None))

    @property
    def email(self):
        return self.user_data.get('email')

    @property
    def username(self):
        return self.user_data.get('username')

    @property
    def balance(self):
        return self.user_data.get('balance', 0.0)

    @staticmethod
    def create_user(email, username, password):
        return {
            'email': email,
            'username': username,
            'password_hash': generate_password_hash(password),
            'balance': 0.0
        }

    @staticmethod
    def check_password(user_data, password):
        return check_password_hash(user_data['password_hash'], password)

def create_bet_document(creator_id, title, description, is_private, min_entry, 
                       max_entry, end_date, outcome_options):
    return {
        'creator_id': ObjectId(creator_id),
        'title': title,
        'description': description,
        'is_private': is_private,
        'min_entry': float(min_entry),
        'max_entry': float(max_entry),
        'total_pot': 0.0,
        'end_date': end_date,
        'status': 'open',
        'outcome_options': outcome_options,
        'correct_outcome': None,
        'participants': []
    }

def create_game_document(creator_id, title, description, end_date, bets):
    """
    bets: list of dictionaries containing bet info
    {
        'title': str,
        'type': 'over_under' | 'binary',
        'line': float,  # for over/under bets
        'odds': {
            'over': float,  # e.g., -110 for standard odds
            'under': float
        }
    }
    """
    return {
        'creator_id': ObjectId(creator_id),
        'title': title,
        'description': description,
        'end_date': end_date,
        'status': 'open',
        'total_pot': 0.0,
        'bets': [
            {
                **bet,
                'total_pot': 0.0,
                'participants': []
            } for bet in bets
        ],
        'created_at': datetime.utcnow()
    }

# Make sure we explicitly define what should be imported
__all__ = ['User', 'create_bet_document', 'create_game_document']
