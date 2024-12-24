from flask import Flask, send_from_directory, jsonify, request, render_template, redirect, url_for, flash
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from pymongo import MongoClient
from models import User, create_bet_document  # This line should now work
from bson import ObjectId
from dotenv import load_dotenv
from datetime import datetime
import os

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, 
    static_folder='static',  # Change static folder
    template_folder='templates'  # Add template folder
)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
CORS(app)

# Initialize MongoDB with URI from .env
client = MongoClient(os.getenv('MONGODB_URI'))
db = client.betterbets

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
    
    return render_template('create_bet.html')

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))