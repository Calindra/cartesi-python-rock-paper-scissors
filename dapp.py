from os import environ
import logging
import json
from challenge import Challenge, Move

from cartesi import DApp, Rollup, RollupData, JSONRouter

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)
dapp = DApp()

# Instantiate the JSON Router
json_router = JSONRouter()

# Register the JSON Router into the DApp
dapp.add_router(json_router)

# From https://github.com/techwithtim/Cartesi-Rock-Paper-Scissors-Project/blob/3293d3c5a2e4b7a298063a7998ce055e84419d81/rock-paper-scissors/main.py#L14C1-L16C12
challenges = {}
player_challenges = {}
next_id = 0

rollup_server = environ["ROLLUP_HTTP_SERVER_URL"]

def add_notice(rollup, data=""):
    logger.info(f"Adding notice {data}")
    resp = rollup.notice("0x" + data.encode('utf-8').hex())
    logger.info(f"Received notice {resp}")

def add_report(rollup, output=""):
    logger.info("Adding report " + output)
    resp = rollup.report("0x" + output.encode('utf-8').hex())
    logger.info(f"Received report {resp}")

@json_router.advance({"method": "create_challenge"})
def create_challenge(rollup: Rollup, data: RollupData) -> bool:
    sender = data.metadata.msg_sender
    payload = data.json_payload()
    global next_id
    commitment = payload.get("commitment")

    if not commitment:
        add_report(rollup, "no commitment")
        return "reject"

    if player_challenges.get(sender) is not None:
        add_report(rollup, "Player is already in a challenge")
        return "reject"
    
    challenge = Challenge(sender, next_id, commitment)
    challenges[next_id] = challenge
    player_challenges[sender] = next_id

    add_notice(rollup, f"challenge with id {next_id} was created by {sender}")
    next_id += 1
    return True

@json_router.advance({"method": "accept_challenge"})
def accept_challenge(rollup: Rollup, data: RollupData) -> bool:
    payload = data.json_payload()
    sender = data.metadata.msg_sender
    commitment = payload.get("commitment")
    challenge_id = payload.get("challenge_id")

    challenge = challenges.get(challenge_id)

    if not challenge:
        add_report(rollup, "challenge does not exist")
        return "reject"
    
    if not commitment:
        add_report(rollup, "no commitment")
        return "reject"

    if player_challenges.get(sender) is not None:
        add_report(rollup, "Player is already in a challenge")
        return "reject"

    challenge.add_opponent(sender, commitment)
    player_challenges[sender] = challenge_id
    add_notice(rollup, f"challenge with id {challenge_id} was accepted by {sender}")
    return True

@json_router.advance({"method": "reveal"})
def reveal(rollup: Rollup, data: RollupData) -> bool:
    sender = data.metadata.msg_sender
    payload = data.json_payload()
    move = payload.get("move")
    nonce = payload.get("nonce")

    challenge_id = player_challenges.get(sender)
    if challenge_id is None:
        add_report(rollup, "challenge does not exist")
        return "reject"
    
    challenge = challenges.get(challenge_id)
    try:
        challenge.reveal(sender, move, nonce)
        add_notice(rollup, f"Challenge {challenge_id}: {sender} revealed their move of {Move.move_to_str(int(move))}")

        if challenge.both_revealed():
            winner = challenge.evaluate_winner()
            if not winner:
                add_notice(rollup, f"Challenge {challenge_id} ended in a draw")
            else:
                add_notice(rollup, f"Challenge {challenge_id} was won by {winner}")

            _delete_challenge(challenge)

        return True
    except Exception as e:
        add_report(rollup, "Error: " + str(e))
        return False

def _delete_challenge(challenge):
    if player_challenges.get(challenge.opponent_address) is not None:
        del player_challenges[challenge.opponent_address]
    
    if player_challenges.get(challenge.creator_address) is not None:
        del player_challenges[challenge.creator_address]

@dapp.inspect()
def get_challenges(rollup: Rollup, data: RollupData) -> bool:
    challenge_keys = challenges.keys()
    challenge_list = []

    for challenge_id in challenge_keys:
        challenge = challenges.get(challenge_id)
        opponent_move = challenge.commitments.get(challenge.opponent_address)
        creator_move = challenge.commitments.get(challenge.creator_address)

        challenge_list.append({
            "challenge_id": challenge_id,
            "creator": challenge.creator_address,
            "opponent": challenge.opponent_address,
            "winner": challenge.winner_address,
            "opponent_committed": challenge.has_opponent_committed(),
            "opponent_move": opponent_move.move if opponent_move else None,
            "creator_move": creator_move.move
        })
    
    output = json.dumps({"challenges": challenge_list})
    add_report(rollup, output)
    return True

if __name__ == '__main__':
    dapp.run()
