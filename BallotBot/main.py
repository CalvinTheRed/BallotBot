import json
import os
import praw
from datetime import datetime, timezone

REDDIT_SITE_NAME = 'vote_bot'
SUBREDDIT_NAME = 'dndhomebrew'
FLAIR_TEXT = 'Meta'
VALID_VOTES = {'yes', 'no', 'indifferent'}
CUTOFF_DATE = datetime(2025, 4, 20, tzinfo=timezone.utc)
COMMENT_DEPTH_CHECK = 50
POST_DEPTH_CHECK = 15
USER_CACHE_FILE = 'known_users.json'
LOG_FILE = 'log.txt'

# Initialize Reddit instance using praw.ini
reddit = praw.Reddit(site_name=REDDIT_SITE_NAME)
subreddit = reddit.subreddit('dndhomebrew')

# TESTED
def load_user_data():
    if not os.path.exists(USER_CACHE_FILE):
        log_action('User cache file not found. Initializing new cache.')
        return {'whitelist': [], 'blacklist': [], 'votes': {}}
    try:
        with open(USER_CACHE_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_action(f'Error loading user cache: {e}')
        return {'whitelist': [], 'blacklist': [], 'votes': {}}

# TESTED
def save_user_data(data):
    try:
        with open(USER_CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        log_action('User cache saved.')
    except Exception as e:
        log_action(f'Error saving user cache: {e}')

# TESTED
def log_action(message):
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    formatted_message = f'[{timestamp}] {message}\n'
    with open(LOG_FILE, 'a') as f:
        f.write(formatted_message)
        print(formatted_message)

# TESTED
def send_modmail(subject, body, recipient):
    try:
        reddit.subreddit(SUBREDDIT_NAME).modmail.create(subject=subject, body=body, recipient=recipient)
        log_action(f'Sent modmail to {recipient}: {subject}')
    except Exception as e:
        log_action(f'Failed to send modmail to {recipient}: {e}')

# TESTED
def get_latest_flaired_post(flair):
    return next(subreddit.search(f'flair:"{flair}"', sort='new', limit=1), None)

# TESTED
def has_prior_activity(author):
    if not author:
        return False

    name = author.name.lower()
    data = load_user_data()

    # Check cache before making requests
    if name in data['whitelist']:
        return True
    if name in data['blacklist']:
        return False

    try:
        # Check user comment history
        for comment in author.comments.new(limit=COMMENT_DEPTH_CHECK):
            comment_created_time = datetime.fromtimestamp(comment.created_utc).replace(tzinfo=timezone.utc)
            if comment.subreddit.display_name.lower() == SUBREDDIT_NAME and comment_created_time < CUTOFF_DATE:
                data['whitelist'].append(name)
                save_user_data(data)
                log_action(f'User {name} added to whitelist via comment history.')
                return True
        # Check user post history
        for submission in author.submissions.new(limit=POST_DEPTH_CHECK):
            submission_created_time = datetime.fromtimestamp(submission.created_utc).replace(tzinfo=timezone.utc)
            if submission.subreddit.display_name.lower() == SUBREDDIT_NAME and submission_created_time < CUTOFF_DATE:
                data['whitelist'].append(name)
                save_user_data(data)
                log_action(f'User {name} added to whitelist via post history.')
                return True
    except Exception as e:
        log_action(f'Error checking prior activity for {name}: {e}')

    # Blacklist user if not active
    data['blacklist'].append(name)
    save_user_data(data)
    log_action(f'User {name} added to blacklist.')
    return False

def monitor_comments(post):
    for comment in subreddit.stream.comments():
        if comment.submission == post:
            author = comment.author
            username = author.name
            content = comment.body.strip().lower()
            if not has_prior_activity(comment.author):
                # Comments made by accounts with insufficient history will be removed and not recorded
                comment.mod.remove()
                log_action(f'Removed comment by {username}: not a known user.')
                send_modmail(
                    'Your Vote Was Removed',
                    (
                        "Your comment was removed because your account hasn't participated in r/DnDHomebrew prior to April 20, 2025. "
                        'If this is a mistake, please [message the moderators]'
                        f'(https://www.reddit.com/message/compose?to=/r/{SUBREDDIT_NAME}) with a link to a post or comment you made '
                        'in the subreddit before the cutoff date.'
                    ),
                    username
                )
            elif content not in VALID_VOTES:
                # Comments made that are not votes will be removed and not recorded
                comment.mod.remove()
                log_action(f'Removed invalid vote comment by {username}: "{content}"')
                send_modmail(
                    username,
                    'Your Vote Was Removed',
                    'Only "yes", "no", or "indifferent" are valid responses in this community vote.'
                )
            else:
                # Comments left by active accounts that are votes will be recorded
                comment.mod.remove()
                data = load_user_data()
                data['votes'][username] = content
                save_user_data(data)
                log_action(f'Recorded vote by {username}: {content}')
                send_modmail(
                    username,
                    'Vote Recorded',
                    (
                        f'Thanks for voting! Your response ({content}) has been recorded. You may change your response at any time',
                        'before the vote ends by re-commenting with your new response.'
                    )
                )
                
            
    print('DONE')

def main():
    return
    
if __name__ == '__main__':
    main()
