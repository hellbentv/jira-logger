#!/usr/bin/env python

###########################################################################
# Based on work from Joyjit Nath
# File: git-jira-hook
# Author: Joyjit Nath
###########################################################################


from __future__ import with_statement

import logging
import sys
import os

myname = os.path.basename(sys.argv[0])

# Change this value to "CRITICAL/ERROR/WARNING/INFO/DEBUG/NOTSET"
# as appropriate.
# loglevel=logging.INFO
loglevel=logging.DEBUG


import contextlib
import subprocess
import re
import collections
import getpass
import SOAPpy
from SOAPpy import structType
import traceback
import pprint
import pdb
import stat
import cookielib
import subprocess
import urllib2
import ConfigParser
import string
import datetime


def main():
    global myname, loglevel
    logging.basicConfig(level=loglevel, format=myname + ":%(levelname)s: %(message)s")

    jira_url = get_jira_url()
    if jira_url == None:
        return

    issuekey = sys.argv[1]
    commit_msg_filename = None#sys.argv[2]
    msg_text = ""

    commit_id = git_get_last_commit_id()
    commit_text = git_get_commit_msg(commit_id)

    if commit_msg_filename is not None:
        try:
            msg_text = open(commit_msg_filename).read()

        except KeyboardInterrupt:
            logging.info('... interrupted')

        except Exception, e:
            logging.error("Failed to open file '%s'", commit_msg_filename)
            logging.debug(e)
            return -1

    (jira_soap_client, jira_auth) = jira_start_session(jira_url)

    make_jira_changes(jira_soap_client, jira_auth, issuekey, msg_text)
    return


def make_jira_changes(jira_soap_client, jira_auth, issuekey, msg_text):
    msg_text = add_git_data(msg_text)
    msg_text = fixupurl(msg_text, 'bug', get_bug_url())
    msg_text = fixupurl(msg_text, 'review', get_review_url())
    jira_log_work(jira_soap_client, jira_auth, issuekey, msg_text)
    jira_add_comment_to_issue(issuekey, jira_soap_client, jira_auth, msg_text)
    return


def jira_log_work(jira_soap_client, jira_auth, issuekey, text):
    magic = re.compile('log' + ' #\w+')
    iterator = magic.finditer(text)
    issue_count = 0
    for match in iterator:
        time = match.group().split(" ", 2)[1].strip('#')
        logging.debug('Time log found in commit message: ' + time)
        d = datetime.datetime.now()
        worklog = {'startDate': SOAPpy.dateTimeType((d.year, d.month, d.day, d.hour, d.minute, 0, 0, 0, 0)), 'timeSpent': time, 'comment': text}
        # print "issuekey found=", issuekey
        jira_soap_client.addWorklogAndAutoAdjustRemainingEstimate(jira_auth, issuekey, worklog)


def add_git_data(text):
    commit_id = git_get_last_commit_id()
    msg = git_get_commit_msg(commit_id)
    return text + '' + msg


def fixupurl(text, pattern, url):
    magic = re.compile(pattern + ' #\d\d*')
    iterator = magic.finditer(text)
    issue_count = 0
    for match in iterator:
        issuekey = match.group().split(" ", 2)[1].strip('#')
        # print "issuekey found=", issuekey
        commit_text_with_url = text.replace('#'+issuekey, "#[" + issuekey + "|" + url + issuekey + "]")
        text = commit_text_with_url
    return text


#-----------------------------------------------------------------------------
# Jira helper functions
#

# Given a Jira server URL (which is stored in git config)
# Starts an authenticated jira session using SOAP api
# Returns a list of the SOAP object and the authentication token
def jira_start_session(jira_url):
    jira_url = jira_url.rstrip("/")
    try:
        handle = urllib2.urlopen(jira_url + "/rpc/soap/jirasoapservice-v2?wsdl")
        soap_client = SOAPpy.WSDL.Proxy(handle)
        # print "self.soap_client set", self.soap_client

    except KeyboardInterrupt:
        logging.info("... interrupted")

    except Exception, e:
        save_jira_cached_auth(jira_url, "")
        logging.error("Invalid Jira URL: '%s'", jira_url)
        logging.debug(e)
        return -1

    auth = jira_login(jira_url, soap_client)
    if auth == None:
        return (None, None)

    return (soap_client, auth)


# Try to use the cached authentication object to log in
# to Jira first. ("implicit")
# if that fails, then prompt the user ("explicit")
# for username/password
def jira_login(jira_url, soap_client):

    auth = get_jira_cached_auth(jira_url)
    if auth != None and auth != "":
        auth = jira_implicit_login(soap_client, auth)
    else:
        auth = None

    if auth == None:
        save_jira_cached_auth(jira_url, "")
        auth = jira_explicit_login(soap_client)

    if auth != None:
        save_jira_cached_auth(jira_url, auth)

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
        sys.stdin = open('/dev/tty', 'r')

        username = raw_input('Jira username: ')
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

            except Exception,e:
                logging.error("User '%s' does not have access to Jira issues")
                return None

        except KeyboardInterrupt:
            logging.info("... interrupted")

        except Exception,e:
            logging.debug("Login failed")

        auth=None
        retry_count = retry_count + 1

    if auth == None:
        logging.error("Invalid Jira password/username combination")

    return auth


def jira_find_issue(issuekey, jira_soap_client, jira_auth, jira_text):
    try:
        issue = jira_soap_client.getIssue(jira_auth, issuekey)
        logging.debug("Found issue '%s' in Jira: (%s)",
                    issuekey, issue["summary"])
        return 0

    except KeyboardInterrupt:
        logging.info("... interrupted")

    except Exception, e:
        logging.error("No such issue '%s' in Jira", issuekey)
        logging.debug(e)
        return -1


def jira_add_comment_to_issue(issuekey, jira_soap_client, jira_auth, jira_text):
    try:
        jira_soap_client.addComment(jira_auth, issuekey, {"body":jira_text})
        logging.debug("Added to issue '%s' in Jira:\n%s", issuekey, jira_text)

    except Exception, e:
        logging.error("Error adding comment to issue '%s' in Jira", issuekey)
        logging.debug(e)
        return -1


#-----------------------------------------------------------------------------
# Miscellaneous Jira related utility functions
#
def get_jira_url():
    return 'http://cards.linaro.org'
    jira_url = git_config_get("jira.url")
    if jira_url == None or jira_url == "":
        logging.error("Jira URL is not set. Please use 'git config jira.url <actual-jira-url> to set it'")
        return None
    return jira_url


def get_jira_cached_auth(jira_url):
    return get_cfg_value(os.environ['HOME'] + "/.jirarc", jira_url, "auth")


def save_jira_cached_auth(jira_url, auth):
    return save_cfg_value(os.environ['HOME'] + "/.jirarc", jira_url, "auth", auth)


#---------------------------------------------------------------------
# Misc. helper functions
#
def get_bug_url():
    return 'https://bugs.linaro.org/show_bug.cgi?id='
    #todo: determine where /when to store the urls
    bug_url = git_config_get("bug.url")
    if bug_url == None or bug_url == "":
        logging.error("Bug URL is not set. Please use 'git config bug.url <actual-bugtracker-url> to set it'")
        return None
    return bug_url


def get_review_url():
    return 'https://review.linaro.org/#/c/'
    #todo: determine where /when to store the urls


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
    except ConfigParser.DuplicateSectionError,e:
        logging.debug("Section '%s' already exists in '%s'", section, cfg_file_name)

    try:
        cfg.set(section, key, value)
    except Exception,e:
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


#----------------------------------------------------------------------------
# git helper functions
#
# Get our current branchname
def git_get_curr_branchname():
    buf = get_shell_cmd_output("git branch --no-color")
    # buf is a multiline output, each line containing a branch name
    # the line that starts with a "*" contains the current branch name

    m = re.search("^\* .*$", buf, re.MULTILINE)
    if m == None:
        return None

    return buf[m.start()+2 : m.end()]


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


#----------------------------------------------------------------------------
# python script entry point. Dispatches main()
if __name__ == "__main__":
  exit (main())

