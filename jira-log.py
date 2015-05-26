#!/usr/bin/env python

# Copyright (C) 2015 Linaro
#
# Author: Alan Bennett <alan.bennett@linaro.org>
#
# This file, jira-logger.py, is a hack, it's not supported
#
# is distributed WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
###########################################################################
# Based on git-jira-hook work from Joyjit Nath
###########################################################################


from __future__ import with_statement

import logging
import sys
import os
import re
import getpass
import SOAPpy
import subprocess
import urllib2
import ConfigParser
import string
import datetime
import argparse

myname = os.path.basename(sys.argv[0])

# Change this value to "CRITICAL/ERROR/WARNING/INFO/DEBUG/NOTSET"
# as appropriate.
loglevel = logging.INFO
# loglevel = logging.DEBUG


def setup_args_parser():
    """Setup the argument parsing.

    :return The parsed arguments.
    """
    print "  The tool will always display 'In Progress' cards so you don't have to use the GUI\n"\
        "  (you can also optionally show all your cards or insert a custom query)\n"\
        "\n"\
        "  The provided comment will be parsed for a few internal strings\n"\
        "     bug #1234  --> creates a jira mark-up link to bugzilla.linaro.org\n"\
        "     review #34  --> creates a jira mark-up link to review.linaro.org\n"\
        "     log #1h  --> the tool will log 1 hour to the Card\n"\
        "\n"\
        "  The target card to log work to and/or comment can be specified on the command line\n"\
        "  and/or parsed out of the local most-recent git commit message\n"
    description = "This is a simple tool for logging work hours and adding comments to cards"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--user", required=False, help="Override the user in the queries")
    parser.add_argument("--inprogress", action="store_true", help="Display only inprogress cards")
    parser.add_argument("--allmycards", action="store_true", help="Display all cards")
    parser.add_argument("--query", required=False, help="Display cards from custom Jira query")
    parser.add_argument("--card", help="Issue # you wish to add a comment to and/or log hours")
    parser.add_argument("--comment", required=False, help="Comment to be added to the CARD")
    parser.add_argument("--hours", help="log hours to the specified card")
    parser.add_argument("--debug", action="store_true")

    return parser.parse_args()


def main():
    global myname, loglevel
    args = setup_args_parser()
    if args.debug is True:
        loglevel = logging.DEBUG
    logging.basicConfig(level=loglevel, format=myname + ":%(levelname)s: %(message)s")

    jira_url = get_jira_url()
    if jira_url is None:
        return

    commit_id = git_get_last_commit_id()
    commit_text = git_get_commit_msg(commit_id)

    (jira_soap_client, jira_auth) = jira_start_session(jira_url)

    if args.user is not None:
        query_username = args.user
    else:
        query_username = get_jira_cached_user()

    if args.query is not None:
        query = args.query
        jira_query_cards(jira_soap_client, jira_auth, query)
    elif args.allmycards is True:
        query = 'assignee="%s" and status not in ("Closed")' % query_username
        jira_query_cards(jira_soap_client, jira_auth, query)
    else:
        query = ('assignee="%s" and status in ("In Progress")' % query_username)
        jira_query_cards(jira_soap_client, jira_auth, query)

    if args.card is not None:
        card = args.card
        logging.debug("CARD (passed in): " + str(card))
    else:
        # check to see if the commit message in the local git repository contains a card reference
        card = check_commit_for_card(commit_text)
        if card is not None:
            logging.debug("CARD (commit msg): " + str(card))
    if card is not None:
        # a card was found, now let's see if we have a comment to add
        msg_text = ""
        if args.comment is not None:
            msg_text = args.comment
            logging.debug("comment: " + str(msg_text))

        if args.hours is not None:
            msg_text += " (log #%dh hours)" % int(args.hours)
            logging.debug("hours: " + str(args.hours))

        if msg_text != "":
            # now if we have a comment and/or hours, update the card
            msg_text = fixup_add_jira_url(msg_text, 'bug', get_bug_url())
            msg_text = fixup_add_jira_url(msg_text, 'review', get_review_url())
            jira_log_work(jira_soap_client, jira_auth, card, msg_text)
            jira_add_comment_to_issue(jira_soap_client, jira_auth, card, msg_text)
    return


def jira_query_cards(jira_soap_client, jira_auth, querystr):
    try:
        logging.debug("CARD Query '%s':\n", querystr)
        matchingcards = jira_soap_client.getIssuesFromJqlSearch(jira_auth, querystr, 50)
        logging.debug("Found %d cards in Jira:\n", len(matchingcards.data))
        print '------------------------------------------------------------------------------'
        print '%d CARDs (%s)' % (len(matchingcards.data), querystr)
        print '------------------------------------------------------------------------------'
        for card in matchingcards.data:
            print '  ' + card["key"] + ': ' + card["summary"]
        print '------------------------------------------------------------------------------'
        return matchingcards.data

    except Exception, e:
        logging.error("Error getting Issues")
        logging.debug(e)
        return -1


def jira_log_work(jira_soap_client, jira_auth, issuekey, text):
    magic = re.compile('log' + ' #\w+')
    iterator = magic.finditer(text)
    for match in iterator:
        time = match.group().split(" ", 2)[1].strip('#')
        logging.info('Adding worklog to %s: %s', issuekey, time)
        d = datetime.datetime.now()
        worklog = {'startDate': SOAPpy.dateTimeType((d.year, d.month, d.day, d.hour, d.minute, 0, 0, 0, 0)),
                   'timeSpent': time, 'comment': text}
        # print "issuekey found=", issuekey
        jira_soap_client.addWorklogAndAutoAdjustRemainingEstimate(jira_auth, issuekey, worklog)


def jira_add_comment_to_issue(jira_soap_client, jira_auth, issuekey, jira_text):
    try:
        jira_soap_client.addComment(jira_auth, issuekey, {"body": jira_text})
        logging.info("Adding comment to Jira '%s' in Jira:\n%s", issuekey, jira_text)

    except Exception, e:
        logging.error("Error adding comment to issue '%s' in Jira", issuekey)
        logging.debug(e)
        return -1


def fixup_add_jira_url(text, pattern, url):
    magic = re.compile(pattern + ' #\d\d*')
    iterator = magic.finditer(text)
    for match in iterator:
        issuekey = match.group().split(" ", 2)[1].strip('#')
        # print "issuekey found=", issuekey
        commit_text_with_url = text.replace('#'+issuekey, "#[" + issuekey + "|" + url + issuekey + "]")
        text = commit_text_with_url
    return text


def check_commit_for_card(text):
    magic = re.compile("refs" + ' #\w\w*-\d\d*')
    iterator = magic.finditer(text)
    issuekey = None
    for match in iterator:
        issuekey = match.group().split(" ", 2)[1].strip('#')
        break
    return issuekey


# -----------------------------------------------------------------------------
# Jira helper functions
#

# Given a Jira server URL (which is stored in git config)
# Starts an authenticated jira session using SOAP api
# Returns a list of the SOAP object and the authentication token
def jira_start_session(jira_url):
    jira_url = jira_url.rstrip("/")
    soap_client = None
    try:
        handle = urllib2.urlopen(jira_url + "/rpc/soap/jirasoapservice-v2?wsdl")
        soap_client = SOAPpy.WSDL.Proxy(handle)
        # print "self.soap_client set", self.soap_client

    except KeyboardInterrupt:
        logging.info("... interrupted")

    except Exception, e:
        save_jira_cached_auth(jira_url)
        save_jira_cached_user(jira_url)
        logging.error("Invalid Jira URL: '%s'", jira_url)
        logging.debug(e)
        return -1

    auth = jira_login(soap_client)
    if auth is None:
        return None, None

    return soap_client, auth


# Try to use the cached authentication object to log in
# to Jira first. ("implicit")
# if that fails, then prompt the user ("explicit")
# for username/password
def jira_login(soap_client):

    auth = get_jira_cached_auth()
    if auth is not None and auth != "":
        auth = jira_implicit_login(soap_client, auth)
    else:
        auth = None

    if auth is None:
        save_jira_cached_auth("")
        auth = jira_explicit_login(soap_client)

    if auth is not None:
        save_jira_cached_auth(auth)

    return auth


def jira_implicit_login(soap_client, auth):

    # test jira to see if auth is valid
    try:
        jira_types = soap_client.getIssueTypes(auth)
        return auth
    except KeyboardInterrupt:
        logging.info("... interrupted")

    except Exception, e:
        print >> sys.stderr, "Previous Jira login is invalid or has expired"
        # logging.debug(e)

    return None


def jira_explicit_login(soap_client):
    max_retry_count = 3
    retry_count = 0
    auth = None
    while retry_count < max_retry_count:
        if retry_count > 0:
            logging.info("Invalid Jira password/username combination, try again")

        # We now need to read the Jira username/password from
        # the console.
        # However, there is a problem. When git hooks are invoked
        # stdin is pointed to /dev/null, see here:
        # http://kerneltrap.org/index.php?q=mailarchive/git/2008/3/4/1062624/thread
        # The work-around is to re-assign stdin back to /dev/tty , as per
        # http://mail.python.org/pipermail/patches/2002-February/007193.html
#        sys.stdin = open('/dev/tty', 'r')

        username = raw_input('Jira username: ')
        save_jira_cached_user(username)
        password = getpass.getpass('Jira password: ')

        # print "abc"
        # print "self.soap_client login...%s " % username + password
        try:
            auth = soap_client.login(username, password)

            try:
                jira_types = soap_client.getIssueTypes(auth)
                return auth

            except KeyboardInterrupt:
                logging.info("... interrupted")

            except Exception, e:
                logging.error("User '%s' does not have access to Jira issues")
                return None

        except KeyboardInterrupt:
            logging.info("... interrupted")

        except Exception, e:
            logging.debug("Login failed")

        auth = None
        retry_count += 1

    if auth is None:
        logging.error("Invalid Jira password/username combination")

    return auth


def jira_find_issue(issuekey, jira_soap_client, jira_auth, jira_text):
    try:
        issue = jira_soap_client.getIssue(jira_auth, issuekey)
        logging.debug("Found issue '%s' in Jira: (%s)", issuekey, issue["summary"])
        return 0

    except KeyboardInterrupt:
        logging.info("... interrupted")

    except Exception, e:
        logging.error("No such issue '%s' in Jira", issuekey)
        logging.debug(e)
        return -1


# -----------------------------------------------------------------------------
# Miscellaneous Jira related utility functions
#
def get_jira_cached_auth():
    return get_cfg_value(os.environ['HOME'] + "/.jirarc", "General", "auth")


def save_jira_cached_auth(auth):
    return save_cfg_value(os.environ['HOME'] + "/.jirarc", "General", "auth", auth)


def get_jira_cached_user():
    return get_cfg_value(os.environ['HOME'] + "/.jirarc", "General", "email")


def save_jira_cached_user(userlogin):
    return save_cfg_value(os.environ['HOME'] + "/.jirarc", "General", "email", userlogin)


# ---------------------------------------------------------------------
# Misc. helper functions
#
def get_jira_url():
    return 'http://cards.linaro.org'


def get_bug_url():
    # todo: Right now this is hard coded, do we want to make it user configurable?
    return 'https://bugs.linaro.org/show_bug.cgi?id='


def get_review_url():
    # todo: Right now this is hard coded, do we want to make it user configurable?
    return 'https://review.linaro.org/#/c/'


def get_cfg_value(cfg_file_name, section, key):
    try:
        cfg = ConfigParser.ConfigParser()
        cfg.read(cfg_file_name)
        value = cfg.get(section, key)
    except:
        return None
    return value


def save_cfg_value(cfg_file_name, section, key, value):
    try:
        cfg = ConfigParser.SafeConfigParser()
    except Exception, e:
        logging.warning("Failed to instantiate a ConfigParser object")
        logging.debug(e)
        return

    try:
        cfg.read(cfg_file_name)
    except Exception, e:
        logging.warning("Failed to read .jirarc")
        logging.debug(e)
        return

    try:
        cfg.add_section(section)
    except ConfigParser.DuplicateSectionError, e:
        logging.debug("Section '%s' already exists in '%s'", section, cfg_file_name)

    try:
        cfg.set(section, key, value)
    except Exception, e:
        logging.warning("Failed to add '%s' to '%s'", key, cfg_file_name)
        logging.debug(e)

    try:
        cfg.write(open(cfg_file_name, 'wb'))
    except Exception, e:
        logging.warning("Failed to write '%s'='%s' to file %s", key, value, cfg_file_name)
        logging.debug(e)
        return


# given a string, executes it as an executable, and returns the STDOUT
# as a string
def get_shell_cmd_output(cmd):
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        return proc.stdout.read().rstrip('\n')
    except KeyboardInterrupt:
        logging.info("... interrupted")

    except Exception, e:
        logging.error("Failed trying to execute '%s'", cmd)


# ----------------------------------------------------------------------------
# git helper functions
#
# Get our current branchname
def git_get_curr_branchname():
    buf = get_shell_cmd_output("git branch --no-color")
    # buf is a multiline output, each line containing a branch name
    # the line that starts with a "*" contains the current branch name

    m = re.search("^\* .*$", buf, re.MULTILINE)
    if m is None:
        return None

    return buf[m.start()+2: m.end()]


def git_config_get(name):
    return get_shell_cmd_output("git config '" + name + "'")


def git_config_set(name, value):
    os.system("git config " + name + " '" + value + "'")


def git_config_unset(name):
    os.system("git config --unset-all " + name)


def git_get_commit_msg(commit_id):
    return get_shell_cmd_output("git rev-list --pretty --max-count=1 " + commit_id)


def git_get_last_commit_id():
    return get_shell_cmd_output("git log --pretty=format:%H -1")


def git_get_array_of_commit_ids(start_id, end_id):
    output = get_shell_cmd_output("git rev-list " + start_id + ".." + end_id)
    if output == "":
        return None

    # parse the result into an array of strings
    commit_id_array = string.split(output, '\n')
    return commit_id_array


# ----------------------------------------------------------------------------
# python script entry point. Dispatches main()
if __name__ == "__main__":
    exit(main())

