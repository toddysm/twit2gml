#!/usr/bin/env python
#-*- coding: utf-8 -*-

"""
:mod: `twit2gml` - Twitter Network export to GML
================================================

    module:: twit2gml
    :platform: Unix, Windows
    :synopsis: Main module for exporting Twitter network information to GML
    moduleauthor:: ToddySM <toddysm@gmail.com>
"""

import argparse
import pickle
import time
import os.path
from twython import Twython
from twython import TwythonError

# GML file name
GML_FILE_NAME = 'twit2gml.gml'

# Twitter API headers
X_RATE_LIMIT_REMAINING = 'x-rate-limit-remaining'
X_RATE_LIMIT_RESET = 'x-rate-limit-reset'

# Globals - those get populated throughout the code
api_key = None
api_secret = None
auth_token = None
auth_secret = None
client = None
screen_name = None

follower_ids = []
follower_names = []
link_matrix = {}

def connect():
    """Establishes a client used to connect to Twitter.
    
    :return: Twitter client
    """
    global client
    client = Twython(app_key = api_key, app_secret = api_secret, \
                          oauth_token = auth_token, oauth_token_secret = auth_secret)

def get_user_profile(screen_name = None, user_id = None):
    """Retrieves the user profile for the specified Twitter user
    
    :param screen_name: Twitter user's screen_name
    :param user_id: Twitter user's ID
    """
    return client.show_user(screen_name = screen_name, user_id = user_id)

def get_trottle_time():
    """Calculates how many seconds the thread should sleep after the last
    call to Twitter.
    
    :return: Sleep time in seconds
    """
    rem_calls = client.get_lastfunction_header(X_RATE_LIMIT_REMAINING)
    next_reset = client.get_lastfunction_header(X_RATE_LIMIT_RESET)
    
    # convert to numbers
    rem_calls = int(0 if rem_calls is None else rem_calls)
    next_reset = int(0 if next_reset is None else next_reset)
    
    # get the current local time in secs
    # Note: Twython converts the UTC returned from Twitter to local
    ts = time.time()
    
    if (next_reset > 0) and (rem_calls > 0):
        # substract the current time from the reset time
        dif = int(next_reset) - ts
        
        # save the time remaining divided by the calls remaining
        sleep_time = dif / int(rem_calls)
    elif (next_reset > 0):
        sleep_time = int(next_reset) - ts
    else:
        sleep_time = 60
    
    # always make sure non-negative value is returned 
    if sleep_time < 0:
        sleep_time = 10     # just in case
    
    print("Sleeping for " + str(sleep_time) + " sec...")
    return sleep_time

def get_followers():
    """Downloads the follower IDs for the user with screen_name.
    
    It stores all the IDs in the global list follower_ids
    """
    global follower_ids
    
    next_cursor = -1
    total = 0
    while True:
        try:
            data = client.get_followers_ids(screen_name=screen_name, cursor=next_cursor)
            follower_ids.extend(data['ids'])
            total += len(data['ids'])
            print("Donwloaded " + str(total) + " follower IDs so far...")
            if data['next_cursor'] == 0 or data['next_cursor'] == data['previous_cursor']:
                break
            else:
                next_cursor = data['next_cursor']
                # sleep if there are more pages to fetch
                time.sleep(get_trottle_time())
        except TwythonError as e:
            print(e)

def get_timeline(screen_name = None, user_id = None):
    """Retrieves the timeline for the specified user
    
    :param screen_name: The screen name for the user
    """
    user_timeline = []
    try:
        max_id = 0        
        timeline = client.get_user_timeline(screen_name = screen_name, user_id = user_id,
                        count=200, exclude_replies=False, trim_user=False, include_rts=True)
        
        while not len(timeline) == 0:
            for tweet in timeline:
                user_timeline.append(tweet)
                max_id = tweet['id'] - 1 # to exclude the last fetched tweet
            
            print("Downloaded " + str(len(user_timeline)) + " tweets for user " + \
                str(screen_name) + "/" + str(user_id) + " so far...")
            
            #sleep before the next API call else we will reach the limit
            time.sleep(get_trottle_time())
            
            timeline = client.get_user_timeline(screen_name = screen_name, user_id = user_id,
                        count=200, exclude_replies=False, trim_user=False, include_rts=True, \
                        max_id = max_id)
    except TwythonError as e:
        print(e)
    
    return user_timeline

def get_profiles(ids):
    """Retrieves the full profiles for the users with the specified IDs
    
    :param ids: The user IDs, whose profiles to retrieve
    
    :return: List of full profiles
    """
    left = 0
    right = 100
    total = 0
    follower_profiles = []
    while True:
        profiles = client.lookup_user(user_id=','.join(str(s) for s in ids[left:right]))
        follower_profiles.extend(profiles)
        total += len(profiles)
        
        print("Downloaded " + str(total) + " profiles so far...")
        
        if len(profiles) < 100:
            break
        else:
            time.sleep(get_trottle_time())
            left = right
            right += 100
    
    return follower_profiles

def build_connections(timeline):
    """Creates connection between the user whos timeline this is and any user
    mentioined in the tweets from the timeling.
    
    The connections are stored into the global link_matrix
    """
    global link_matrix
    
    for tweet in timeline:
        user_name = tweet['user']['screen_name']
        
        if tweet['in_reply_to_screen_name'] and tweet['in_reply_to_screen_name'] \
        in follower_names and not tweet['in_reply_to_screen_name'] == user_name:
            if user_name in link_matrix.keys():
                # user already has links
                link_matrix[user_name].append(tweet['in_reply_to_screen_name'])
            else:
                # create new list of connections for this user
                temp_list = [tweet['in_reply_to_screen_name']]
                link_matrix[user_name] = temp_list

def create_node_str(node_id):
    """Creates node for the GML file
    
    :param node_id: The id of the node
    """
    node_str = "\tnode\n\t[\n\t\tid " + str(node_id) + "\n\t]\n"
    return node_str

def create_edge_str(source_id, target_id):
    """Creates edge for the GML file
    
    :param source_id: The id of the source node
    :param target_id: The id of the target node
    """
    edge_str = "\tedge\n\t[\n\t\tsource " + str(source_id) + "\n"
    edge_str += "\t\ttarget " + str(target_id) + "\n\t]\n"
    return edge_str

def build_gml():
    """Builds GML file from the link matrix"""
    
    # open the file
    gml_file = open(GML_FILE_NAME, 'w+')
    
    # write the initial string
    gml_file.write("graph\n[\n")
    
    # create the nodes
    for screen_name in follower_names:
        node_str = create_node_str(screen_name)
        gml_file.write(node_str)
    
    # create the edges
    for screen_name in link_matrix.keys():
        # if the user has links
        if link_matrix[screen_name]:
            link_set = set(link_matrix[screen_name])    # unique set
            
            # create the edges
            for link in link_set:
                edge_str = create_edge_str(screen_name, link)
                gml_file.write(edge_str)
    
    # write the closing bracket
    gml_file.write("]")
    
    #close the file
    gml_file.close()

if __name__ == '__main__':
    """This is the main program entry. You can call it by using the following
    command line arguments:
        -k KEY, --key KEY
                Twitter API key
        -s SECRET, --secret SECRET
                Twitter API secret
        -at AUTH_TOKEN, --auth_token AUTH_TOKEN
                Twitter API authorization token
        -as AUTH_SECRET, --auth_secret AUTH_SECRET
                Twitter API authorization secret
        -sn SCREEN_NAME, --screen_name SCREEN_NAME
                Twitter screen_name
    """
    parser = argparse.ArgumentParser(description='Exports the user\'s Twitter network to GML')
    parser.add_argument('-k', '--key', help='Twitter API key', required=True)
    parser.add_argument('-s', '--secret', help='Twitter API secret', required=True)
    parser.add_argument('-at', '--auth_token', help='Twitter API authorization token', required=True)
    parser.add_argument('-as', '--auth_secret', help='Twitter API authorization secret', required=True)
    parser.add_argument('-sn', '--screen_name', help='Twitter screen_name', required=True)
    
    args = parser.parse_args()
    
    # populate the globals
    api_key = args.key
    api_secret = args.secret
    auth_token = args.auth_token
    auth_secret = args.auth_secret
    screen_name = args.screen_name
    print("Initialization completed! Establishing Twitter client...")
    
    completed = False
    while not completed:
        try:
            connect()
            print("Twitter client created! Downloading followers for user '" + \
                screen_name + "'...")
            
            # store the user ID into the list of followers
            user_profile = get_user_profile(screen_name = screen_name)
            follower_ids.append(user_profile['id'])
            
            get_followers()
            #convert to a set for faster access
            #follower_ids = set(follower_ids)
            print("Retrieved list of followers! Downloading profiles...")
            
            # download the profiles for the followers
            if not os.path.isfile('screen.names'):    
                profiles = None
                if not os.path.isfile('users.profiles'):
                    profiles = get_profiles(follower_ids)
                    pickle.dump(profiles, open('users.profiles', 'wb'))
                    print("Retrieved user profiles! Extracting the screen names...")
                
                # iterate over the profiles and store the screen names
                if not profiles:
                    profiles = pickle.load(open('users.profiles', 'rb'))
                
                for profile in profiles:
                    follower_names.append(profile['screen_name'])
                
                pickle.dump(follower_names, open('screen.names', 'wb'))
            else:
                follower_names = pickle.load(open('screen.names', 'rb'))
            
            # download the timelines and save in temporary files
            for name in follower_names:
                if not os.path.isfile(name + '.timeline'):
                    user_timeline = get_timeline(screen_name = name)
                    if not len(user_timeline) == 0:
                        pickle.dump(user_timeline, open(name + '.timeline', 'wb'))
                        print("Retreived timeline for user '" + name + "'")
                    else:
                        print("Timeline for user '" + name + "' is emtpy or couldn't be retrieved!")
            
            # it is only complete when it reaches this statement :)
            completed = True
        except Exception as e:
            print(e)
    
    # load the timelines from the temp files and build the connection matrix
    for name in follower_names:
        if os.path.isfile(name + '.timeline'):
            user_timeline = pickle.load(open(name + '.timeline', 'rb'))
            build_connections(user_timeline)
            print("Built connections for user '" + name + "'")
    
    print("Link matrix created! Creating the GML file...")
    
    build_gml()
    
    print("Complete!")
    print("You can find the twit2gml.gml file in the current folder")