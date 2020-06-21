
from flask import Flask, request, jsonify
import copy
import json
import os
import time
import uuid


DB_FILENAME = 'game_history.json'


class Record(object):

    def __init__(self, scoreboard, session_id=None):    
        '''Create a game record object

        Params
        ------
        scoreboard : list
            Ordered list from winner to loser.

        session_id : str
            Name / ID for the session in which this record occurred.
        '''
        self.timestamp = time.asctime()
        self.scoreboard = scoreboard
        self.session_id = session_id

    def json(self):
        return {'timestamp': self.timestamp, 
                'scoreboard': self.scoreboard, 
                'session_id': self.session_id}


class Session(object):

    def __init__(self): 
        '''Create a Session object'''
        self.start_time = time.asctime()
        self.session_id = str(uuid.uuid4())
        self.end_time = None
        self.game_count = 0

    def end(self):
        self.end_time = time.asctime()
        return self.json()

    def json(self):
        return {'session_id': self.session_id, 
                'start_time': self.start_time, 
                'end_time': self.end_time,
                'game_count': self.game_count}      


app = Flask(__name__)
app.history = {
    'games': [],
    'sessions': []
}

app.state = {
    'session': None
}


if os.path.exists(DB_FILENAME):
    with open(DB_FILENAME) as fh:
        app.history.update(**json.load(fh))


def this_session():
    # If we're not in an explicit session, make one
    if app.state['session'] is None:
        app.state['session'] = Session()
    
    return app.state['session']


def this_sessions_games():
    return filter(lambda row: row['session_id'] == this_session().session_id, 
                  app.history['games'])


def save_history(history, filename):
    with open(filename, 'w') as fh:
        json.dump(history, fh, indent=2)


def start_session():
    '''Start a game session.

    Returns
    -------
    msg : str
        Human-readable response.
    '''
    return "Session started at {}".format(this_session().start_time)


def end_session():
    '''Close the open session.
    
    Returns
    -------
    msg : str
        Human-readable response.
    '''
    app.history['sessions'].append(this_session().end())
    save_history(app.history, DB_FILENAME)
    games = this_sessions_games()
    winner = get_winner(games)
    msg = ("Session ended at {} after {} games. Winner is {}!"
           .format(this_session().end_time,
                   this_session().game_count,
                   winner))

    app.state['session'] = None
    return msg


def get_wins(games):
    wins = {}
    for result in games:
        scoreboard, session_id = [result[k] for k in ('scoreboard', 'session_id')]
        
        if scoreboard[0] not in wins:
            wins[scoreboard[0]] = 0
        wins[scoreboard[0]] += 1
    return wins


def get_winner(games):
    sorted_results = sorted([(v, k) for (k, v) in get_wins(games).items()])
    return sorted_results[-1][1]


def summarize(games):
    player_points = {}
    total_games = 0
    player_games = {}

    for result in games:
        scoreboard, session_id = [result[k] for k in ('scoreboard', 'session_id')]
        num_players = len(scoreboard)

        for n, name in enumerate(scoreboard, 1):
            if name not in player_points:
                player_points[name] = 0

            player_points[name] += num_players - n

            if name not in player_games:
                player_games[name] = 0

            player_games[name] += 1
        total_games += 1

    return {'player_points': player_points, 'player_games': player_games}


def pretty_print(stats):

    points_per_game = []
    for name in stats['player_games']:
        points_per_game += [(name, stats['player_points'].get(name, 0.0)/stats['player_games'][name])]

    points_per_game = sorted(points_per_game, key=lambda x: x[1], reverse=True)

    return '\n'.join(['{0}: {1:0.3f}'.format(*x) for x in points_per_game])


@app.route('/session', methods=['POST'])
def manage_session():
    '''Start and end a game session.'''

    # Parse Request
    request.get_data()
    app.logger.info(request.form)
    command = request.form.get('text').lower().strip()

    if command == 'start':
        msg = start_session()
    elif command == 'end':
        msg = end_session()
    else:
        msg = "Try again! `/session` only accepts 'start' and 'end'"

    save_history(app.history, DB_FILENAME)

    return jsonify({'text': msg, 'response_type': 'in_channel'})


@app.route('/gameover', methods=['POST'])
def log_result():
    '''Receives a space-separated list of 1st to last place players.
    '''

    # Parse request
    request.get_data()
    app.logger.info(request.form)
    scoreboard = request.form.get('text').split()

    # Log the game
    record = Record(scoreboard=scoreboard, 
                    session_id=this_session().session_id)
    this_session().game_count += 1
    app.history['games'].append(record.json())

    save_history(app.history, DB_FILENAME)

    # Update summary stats
    winner = scoreboard[0]
    losers = ' and '.join(scoreboard[1:])
    stat_str = """
    *Session wins:* {}

    *All Time Points:*
    {}
    """.format(get_wins(this_sessions_games()), 
               pretty_print(summarize(app.history['games'])))

    return jsonify({'text': 'Got it! {} beat {}\n{}'.format(winner, losers, stat_str),
                    'response_type': 'in_channel'})
