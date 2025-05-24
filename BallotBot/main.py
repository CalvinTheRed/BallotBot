import json
import os
import praw
import threading
from datetime import datetime, timezone

REDDIT_SITE_NAME = 'ballot_bot'
SUBREDDIT_NAME = 'dndhomebrew'
FLAIR_TEXT = 'Official'
VALID_VOTES = {'yes', 'no'}
CUTOFF_DATE = datetime(2025, 4, 20, tzinfo=timezone.utc)
ACTIVITY_DEPTH_CHECK = 100
USER_CACHE_FILE = 'known_users.json'
LOG_FILE = 'log.txt'

user_data_lock = threading.Lock()

# Initialize Reddit instance using praw.ini
reddit = praw.Reddit(site_name=REDDIT_SITE_NAME)
subreddit = reddit.subreddit('dndhomebrew')

def load_user_data():
    if not os.path.exists(USER_CACHE_FILE):
        log_action('User cache file not found. Initializing new cache.')
        return {'whitelist': [], 'blacklist': [], 'votes': {}}
    try:
        with open(USER_CACHE_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        log_action(f'Error loading user cache: {e}', print_to_screen=True)
        return {'whitelist': [], 'blacklist': [], 'votes': {}}

def save_user_data(data):
    try:
        with open(USER_CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log_action(f'Error saving user cache: {e}', print_to_screen=True)

def log_action(message, print_to_screen=False):
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    formatted_message = f'[{timestamp}] {message}\n'
    with open(LOG_FILE, 'a') as f:
        f.write(formatted_message)
        if (print_to_screen):
            print(formatted_message)

def send_modmail(recipient, subject, body):
    try:
        reddit.subreddit(SUBREDDIT_NAME).modmail.create(subject=subject, body=body, recipient=recipient).archive()
        log_action(f'Sent modmail to {recipient}: {subject}')
    except Exception as e:
        log_action(f'Failed to send modmail to {recipient}: {e}', print_to_screen=True)

def get_latest_post_by_flair(flair):
    return next(subreddit.search(f'flair:"{flair}"', sort='new', limit=1), None)

def get_post_by_title(title):
    return next(subreddit.search(f'title:"{title}"', sort='new', limit=1), None)

def has_prior_activity(author):
    if not author:
        return False

    name = author.name.lower()
    with user_data_lock:
        data = load_user_data()

        # Check cache before making requests
        if name in data['whitelist']:
            return True
        if name in data['blacklist']:
            return False

        try:
            # Check user comment history
            for comment in author.comments.new(limit=ACTIVITY_DEPTH_CHECK):
                comment_created_time = datetime.fromtimestamp(comment.created_utc).replace(tzinfo=timezone.utc)
                if comment.subreddit.display_name.lower() == SUBREDDIT_NAME and comment_created_time < CUTOFF_DATE:
                    data['whitelist'].append(name)
                    save_user_data(data)
                    log_action(f'User {name} added to whitelist via comment history.')
                    return True
            # Check user post history
            for submission in author.submissions.new(limit=ACTIVITY_DEPTH_CHECK):
                submission_created_time = datetime.fromtimestamp(submission.created_utc).replace(tzinfo=timezone.utc)
                if submission.subreddit.display_name.lower() == SUBREDDIT_NAME and submission_created_time < CUTOFF_DATE:
                    data['whitelist'].append(name)
                    save_user_data(data)
                    log_action(f'User {name} added to whitelist via post history.')
                    return True
        except Exception as e:
            log_action(f'Error checking prior activity for {name}: {e}', print_to_screen=True)

        # Blacklist user if not active
        data['blacklist'].append(name)
        save_user_data(data)
        log_action(f'User {name} added to blacklist.')
        return False

def monitor_comments(post):
    for comment in subreddit.stream.comments():
        try:
            if comment.submission == post:
                author = comment.author
                username = author.name
                content = comment.body.strip().lower()
                if not has_prior_activity(comment.author):
                    # Comments made by accounts with insufficient history will be removed and not recorded
                    comment.mod.remove()
                    log_action(f'Removed comment by {username}: not a known user.')
                    send_modmail(
                        username,
                        'Your Vote Was Removed',
                        f"Your comment was removed because your account hasn't participated in r/DnDHomebrew prior to April 20, 2025. If this is a mistake, please [message the moderators](https://www.reddit.com/message/compose?to=/r/{SUBREDDIT_NAME}) with a link to a post or comment you made in the subreddit before the cutoff date."
                    )
                elif content not in VALID_VOTES:
                    # Comments made that are not votes will be removed and not recorded
                    comment.mod.remove()
                    log_action(f'Removed invalid vote comment by {username}: "{content}"')
                    send_modmail(
                        username,
                        'Your Vote Was Removed',
                        'Only "yes" and "no" are valid responses in this community vote.'
                    )
                else:
                    # Comments left by active accounts that are votes will be recorded
                    comment.mod.remove()
                    with user_data_lock:
                        data = load_user_data()
                        data['votes'][username] = content
                        save_user_data(data)
                        log_action(f'Recorded vote by {username}: {content}')
                        send_modmail(
                            username,
                            'Vote Recorded',
                            f'Thanks for voting! Your response ({content}) has been recorded. You may change your response at any time before the vote ends by re-commenting with your new response.'
                        )
        except Exception as e:
            log_action(f'Encountered an error: {e}', print_to_screen=True)

def monitor_terminal():
    # Check terminal for commands
    while True:
        try:
            cmd = input().strip().lower()
            # whitelist <username>
            if cmd.startswith('whitelist '):
                username = cmd.split(' ', 1)[1].strip()
                with user_data_lock:
                    data = load_user_data()
                    if username not in data['whitelist']:
                        data['whitelist'].append(username)
                        log_action(f'User {username} added to whitelist via terminal.', print_to_screen=True)
                    if username in data['blacklist']:
                        data['blacklist'].remove(username)
                        log_action(f'User {username} removed from blacklist.', print_to_screen=True)
                    save_user_data(data)
                    send_modmail(
                        username,
                        'User Added to Whitelist',
                        f'You have been added to the whitelist for the community vote! Thank you for your patience. Comment on the post again to cast your vote.'
                    )
            # exit
            elif cmd == 'exit':
                print('Closing script')
                os._exit(0)
        except Exception as e:
            log_action(f'Error processing terminal command: {e}', print_to_screen=True)

def main():
    threading.Thread(target=monitor_terminal, daemon=True).start()
    post = get_latest_post_by_flair(FLAIR_TEXT)
    monitor_comments(post)
    
if __name__ == '__main__':
    main()
