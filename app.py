from flask import Flask, send_from_directory, jsonify, request, render_template, redirect, url_for, flash
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from pymongo import MongoClient
from models import User, create_bet_document
from bson import ObjectId
from dotenv import load_dotenv
from datetime import datetime
import os
import certifi
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__, 
    static_folder='static',
    template_folder='templates'
)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
CORS(app)

# Initialize MongoDB with proper error handling
MONGODB_URI = os.getenv('MONGODB_URI')
if not MONGODB_URI:
    logger.error("MONGODB_URI not found in environment variables.")
    raise EnvironmentError("MONGODB_URI not found in environment variables.")

try:
    client = MongoClient(MONGODB_URI)
    # Test the connection
    client.admin.command('ping')
    db = client.betterbets
    logger.info("Connected to MongoDB successfully.")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    raise e

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    user_data = db.users.find_one({'_id': ObjectId(user_id)})
    return User(user_data) if user_data else None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Handle API requests (JSON data)
        if request.is_json:
            data = request.json
            user_data = db.users.find_one({'email': data['email']})
            if user_data and User.check_password(user_data, data['password']):
                login_user(User(user_data))
                return jsonify({'message': 'Logged in successfully'})
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Handle form submissions
        email = request.form.get('email')
        password = request.form.get('password')
        user_data = db.users.find_one({'email': email})
        
        if user_data and User.check_password(user_data, password):
            login_user(User(user_data))
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        flash('Invalid email or password.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Handle API requests (JSON data)
        if request.is_json:
            data = request.json
            if db.users.find_one({'email': data['email']}):
                return jsonify({'error': 'Email already registered'}), 400
            
            user_data = User.create_user(
                email=data['email'],
                username=data['username'],
                password=data['password']
            )
            result = db.users.insert_one(user_data)
            user_data['_id'] = result.inserted_id
            login_user(User(user_data))
            return jsonify({'message': 'Registered successfully'})
        
        # Handle form submissions
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        
        if db.users.find_one({'email': email}):
            flash('Email already registered.', 'error')
            return render_template('register.html')
        
        user_data = User.create_user(email, username, password)
        result = db.users.insert_one(user_data)
        user_data['_id'] = result.inserted_id
        login_user(User(user_data))
        flash('Registration successful!', 'success')
        return redirect(url_for('index'))
    
    return render_template('register.html')

@app.route('/api/bets', methods=['GET'])
@login_required
def get_bets():
    bets = list(db.bets.find({'status': 'open'}))
    for bet in bets:
        bet['id'] = str(bet['_id'])
        del bet['_id']
    return jsonify(bets)

@app.route('/bet/create', methods=['GET', 'POST'])
@login_required
def create_bet():
    # Get all available games from the database
    games = list(db.games.find({'status': 'open'}))
    
    if request.method == 'POST':
        # Handle API requests (JSON data)
        if request.is_json:
            data = request.json
            bet = create_bet_document(
                creator_id=current_user.id,
                title=data['title'],
                description=data['description'],
                is_private=data['isPrivate'],
                min_entry=data['minEntry'],
                max_entry=data['maxEntry'],
                end_date=data['endDate'],
                outcome_options=data['outcomeOptions']
            )
            result = db.bets.insert_one(bet)
            return jsonify({'id': str(result.inserted_id)})
        
        # Handle form submissions
        try:
            bet = create_bet_document(
                creator_id=current_user.id,
                title=request.form.get('title'),
                description=request.form.get('description'),
                is_private=bool(request.form.get('is_private')),
                min_entry=float(request.form.get('min_entry')),
                max_entry=float(request.form.get('max_entry')),
                end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%dT%H:%M'),
                outcome_options=request.form.getlist('outcome_options')
            )
            db.bets.insert_one(bet)
            flash('Bet created successfully!', 'success')
            return redirect(url_for('index'))
        except ValueError as e:
            flash(f'Error creating bet: {str(e)}', 'error')
            return render_template('create_bet.html')
    
    return render_template('create_bet.html', games=games)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/bet/<bet_id>/join', methods=['POST'])
@login_required
def join_bet(bet_id):
    bet = db.bets.find_one({'_id': ObjectId(bet_id)})
    if not bet:
        flash('Bet not found.', 'error')
        return redirect(url_for('index'))
    
    amount = float(request.form.get('amount'))
    if amount < bet['min_entry'] or amount > bet['max_entry']:
        flash(f'Amount must be between ${bet["min_entry"]} and ${bet["max_entry"]}.', 'error')
        return redirect(url_for('bet_details', bet_id=bet_id))
    
    # Update user's balance and bet participation
    db.users.update_one(
        {'_id': ObjectId(current_user.id)},
        {'$inc': {'balance': -amount}}
    )
    
    db.bets.update_one(
        {'_id': ObjectId(bet_id)},
        {
            '$inc': {'total_pot': amount},
            '$push': {
                'participants': {
                    'user_id': ObjectId(current_user.id),
                    'amount': amount,
                    'selected_outcome': request.form.get('selected_outcome'),
                    'timestamp': datetime.utcnow()
                }
            }
        }
    )
    
    flash('Successfully joined the bet!', 'success')
    return redirect(url_for('bet_details', bet_id=bet_id))

@app.route('/bet/<bet_id>')
def bet_details(bet_id):
    bet = db.bets.find_one({'_id': ObjectId(bet_id)})
    if not bet:
        flash('Bet not found.', 'error')
        return redirect(url_for('index'))
    
    creator = db.users.find_one({'_id': bet['creator_id']})
    return render_template('bet_details.html', bet=bet, creator=creator)

# Update index route to show bets
@app.route('/')
def index():
    bets = list(db.bets.find({'status': 'open'}))
    return render_template('index.html', bets=bets)

# Add static file handling
@app.route('/<path:path>')
def static_file(path):
    return send_from_directory('static', path)

def calculate_processing_fee(amount):
    """Calculate processing fee for deposit amount"""
    percentage_fee = 0.029  # 2.9%
    fixed_fee = 0.30       # $0.30
    return (amount * percentage_fee) + fixed_fee

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
            if amount < 5 or amount > 1000:
                flash('Amount must be between $5 and $1000', 'error')
                return render_template('deposit.html')

            processing_fee = calculate_processing_fee(amount)
            total_amount = amount + processing_fee

            # Update user's balance with the actual deposit amount
            db.users.update_one(
                {'_id': ObjectId(current_user.id)},
                {'$inc': {'balance': amount}}
            )
            
            flash(f'Successfully added ${amount:.2f} to your account! (Processing fee: ${processing_fee:.2f})', 'success')
            return redirect(url_for('index'))
            
        except ValueError:
            flash('Invalid amount specified', 'error')
            return render_template('deposit.html')
            
    return render_template('deposit.html')

@app.route('/game/create', methods=['GET', 'POST'])
@login_required
def create_game():
    if request.method == 'POST':
        try:
            betting_lines = []
            form_data = request.form.to_dict(flat=False)
            line_count = len([k for k in form_data.keys() if k.startswith('lines[') and k.endswith('].title')])
            
            for i in range(line_count):
                line = {
                    'title': request.form.get(f'lines[{i}].title'),
                    'options': [
                        {
                            'title': request.form.get(f'lines[{i}].option1_title'),
                            'odds': float(request.form.get(f'lines[{i}].option1_odds')),
                            'multiplier': float(request.form.get(f'lines[{i}].option1_multiplier'))
                        },
                        {
                            'title': request.form.get(f'lines[{i}].option2_title'),
                            'odds': float(request.form.get(f'lines[{i}].option2_odds')),
                            'multiplier': float(request.form.get(f'lines[{i}].option2_multiplier'))
                        }
                    ]
                }
                betting_lines.append(line)

            game = {
                'creator_id': ObjectId(current_user.id),
                'title': request.form.get('title'),
                'description': request.form.get('description'),
                'betting_lines': betting_lines,
                'end_date': datetime.strptime(request.form.get('end_date'), '%Y-%m-%dT%H:%M'),
                'status': 'open',
                'created_at': datetime.utcnow()
            }
            
            db.games.insert_one(game)
            flash('Game created successfully!', 'success')
            return redirect(url_for('index'))
            
        except (ValueError, TypeError) as e:
            flash(f'Error creating game: {str(e)}', 'error')
            return render_template('create_game.html')
    
    return render_template('create_game.html')

@app.route('/games')
def list_games():
    games = list(db.games.find({'status': 'open'}))
    return render_template('games.html', games=games)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
