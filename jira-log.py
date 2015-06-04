#!/usr/bin/python
# __author__ = 'akbennett'
import argparse
import configure as config
import datetime
from jira.client import JIRA
import logging
import subprocess
import re

conf_file = "~/.jira-log.rc"
DEFAULT_LOGGER_NAME = "cardwalk.log"


def connect_jira(jira_server, jira_user, jira_pass, logger):
    """Connect to Jira Instance
    """
    try:
        logger.info("Connection to JIRA %s" % jira_server)
        jira_options = {'server': 'https://' + jira_server}
        jira = JIRA(options=jira_options, basic_auth=(jira_user, jira_pass))
        return jira
    except ConnectionError as e:
        logger.error("Failed to connect to JIRA: %s" % e)
        return None


def get_logger(name=DEFAULT_LOGGER_NAME, debug=False):
    """setup logger
    """
    logger = logging.getLogger(name)
    ch = logging.StreamHandler()

    if debug:
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        logger.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter("%(message)s")
        ch.setFormatter(formatter)
        logger.setLevel(logging.INFO)

    logger.addHandler(ch)
    return logger


def setup_args_parser():
    """Setup the argument parsing.

    :return The parsed arguments.
    """
    print "Common Commands\n"\
          "===============\n"\
          " Show me the available epics / engineering cards\n"\
          "    ./jira-log.py --epic\n"\
          " Add a comment and log 3 hours of work\n"\
          "    ./jira-log.py --issue LAVA-1608 --comment 'more work' --hours 3\n"\
          " Create a new sub-task card under Blueprint LAVA-1590\n"\
          "    ./jira-log.py --createsubtask LAVA-1590 'Bug 3232'\n"\
          " Create a new blueprint under epic LAVA-1608\n"\
          "    ./jira-log.py --createblueprint LAVA-1608 'Implement feature X'\n"


    description = "This is a simple tool for logging work hours and adding comments to cards"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--user", "-u", required=False, help="Override the user in the queries")
    parser.add_argument("--inprogress", action="store_true", help="Display only inprogress cards")
    parser.add_argument("--allmycards", action="store_true", help="Display all cards")
    parser.add_argument("--epics", required=False, help="Display all project Epics")
    parser.add_argument("--createsubtask", nargs=2, required=False, help="[blueprint id] ['Summary string']")
    parser.add_argument("--createblueprint", nargs=2, required=False, help="[epic id] ['Summary String']")
    parser.add_argument("--query", "-q", required=False, help="Display cards from custom Jira query")
    parser.add_argument("--issue", "-i", help="Issue # you wish to add a comment to and/or log hours")
    parser.add_argument("--comment", "-c", required=False, help="Comment to be added to the CARD")
    parser.add_argument("--hours", "-hour", help="log hours to the specified card")
    parser.add_argument("--debug", "-d", action="store_true")

    return parser.parse_args()


def main():
    args = setup_args_parser()
    global logger
    logger = get_logger(debug=args.debug)

    conf = config.default_config(conf_file)
    jira_server = conf.get('jira_default', 'host')
    jira_user = conf.get('jira_default', 'username')
    jira_pass = conf.get('jira_default', 'password')
    jira = connect_jira(jira_server, jira_user, jira_pass, logger)
    if jira is None:
        return

    commit_text = None
    commit_id = git_get_last_commit_id()
    if commit_id is not None:
        commit_text = git_get_commit_msg(commit_id)

    if args.user is not None:
        query_username = args.user
    else:
        query_username = jira_user

    if args.query is not None:
        query = args.query
        jira_query_cards(jira, query)
    elif args.allmycards is True:
        query = 'assignee="%s" and status not in ("Closed")' % query_username
        jira_query_cards(jira, query)
    elif args.epics is not None:
        query = 'project=%s and type="Engineering Card" and status not in (Resolved, Closed)' % args.epics
        jira_query_cards(jira, query)
    elif args.createsubtask is not None:
        parent = args.createsubtask[0]
        summary = args.createsubtask[1]
        jira_create_subtask(jira, parent, summary, query_username)
    elif args.createblueprint is not None:
        epic = args.createblueprint[0]
        summary = args.createblueprint[1]
        jira_create_blueprint(jira, epic, summary, query_username)
    else:
        query = 'assignee="%s" and status in ("In Progress")' % query_username
        jira_query_cards(jira, query)

    if args.issue is not None:
        card = args.issue
        logging.debug("CARD (passed in): %s " % str(card))
    else:
        # check to see if the commit message in the local git repository contains a card reference
        card = check_commit_for_card(commit_text)
        if card is not None:
            logging.debug("CARD (commit msg): %s " % str(card))

    if card is not None:
        # a card was found, now let's see if we have a comment to add
        msg_text = ""
        if args.comment is not None:
            msg_text = args.comment
            logging.debug("comment: %s " % str(msg_text))

        if args.hours is not None:
            msg_text += " (log #%dh hours)" % int(args.hours)
            logging.debug("hours: %s " % str(args.hours))

        if msg_text != "":
            # now if we have a comment and/or hours, update the card
            msg_text = fixup_add_jira_url(msg_text, 'bug', get_bug_url())
            msg_text = fixup_add_jira_url(msg_text, 'review', get_review_url())
            jira_log_work(jira, card, msg_text)
            jira_add_comment_to_issue(jira, card, msg_text)
    return


# ---------------------------------------------------------------------
# Jira. helper functions
#
def jira_query_cards(jira, querystr):
    try:
        logging.debug("CARD Query '%s':\n", querystr)
        issues = jira.search_issues(querystr)
        logging.debug("Found %d cards in Jira:\n", len(issues))
        print '------------------------------------------------------------------------------'
        print '%d CARDs (%s)' % (len(issues), querystr)
        print '------------------------------------------------------------------------------'
        for card in issues:
            print '  ' + card.key + ': ' + card.fields.summary
        print '------------------------------------------------------------------------------'
        return issues

    except Exception, e:
        logging.error("Error getting Issues")
        logging.debug(e)
        return -1


def jira_log_work(jira, issuekey, text):
    magic = re.compile('log' + ' #\w+')
    iterator = magic.finditer(text)
    for match in iterator:
        time = match.group().split(" ", 2)[1].strip('#')
        logging.info('Adding worklog to %s: %s', issuekey, time)
        d = datetime.datetime.now()
        jira.add_worklog(issue=issuekey, timeSpent=time, comment=text)
        print 'Adding worklog to %s: %s' % (issuekey, time)


def jira_add_comment_to_issue(jira, issuekey, jira_text):
    try:
        jira.add_comment(issuekey, jira_text)
        logging.info("Adding comment to Jira '%s' in Jira:\n%s", issuekey, jira_text)

    except Exception, e:
        logging.error("Error adding comment to issue '%s' in Jira", issuekey)
        logging.debug(e)
        return -1


def jira_create_blueprint(jira, epic, summary, assignee):
    blueprint = None
    try:
        epic_issue = jira.issue(epic)
        new_issue = {
            'project': {'key': epic_issue.fields.project.key},
            'summary': summary,
            'description': 'Created by jira-logger under epic: %s' % epic_issue,
            'issuetype': {'name': 'Blueprint'},
            'assignee': {'name': assignee},
            }
        blueprint = jira.create_issue(fields=new_issue)
        logging.info("issue created: %s\n" % blueprint)
    except Exception, e:
        logging.error("Error adding subtask to issue '%s' in Jira", parent)
        logging.debug(e)
        return -1

    try:
        if blueprint is not None:
            jira.transition_issue(blueprint, '21')
            logging.info("transitioned to 'In Progress'\n")
    except Exception, e:
        logging.error("Error transitioning subtask to issue '%s' in Jira", blueprint)
        logging.debug(e)
        return -1

    try:
        if blueprint is not None:
            #jira.add_issues_to_epic(epic_id, issue_keys, ignore_epics=True)[source]
            fields = [blueprint.key]
            jira.add_issues_to_epic(epic, fields)
            logging.info("added to %s to epic %s \n" % (blueprint.key, epic))
    except Exception, e:
        logging.error("Error transitioning blueprint to issue '%s' in Jira", blueprint)
        logging.debug(e)
        return -1
    print "Blueprint:%s created under epic:%s and transitioned to In-progress" % (blueprint, epic)


def jira_create_subtask(jira, parent, summary, assignee):
    child = None
    try:
        parent_issue = jira.issue(parent)
        subtask = {
            'project': {'key': parent_issue.fields.project.key},
            'summary': summary,
            'description': 'Created by jira-logger',
            'issuetype': {'name': 'Sub-task'},
            'parent': {'id': parent},
            'assignee': {'name': assignee},
            }
        child = jira.create_issue(fields=subtask)
        logging.info("issue created: %s\n" % child)
    except Exception, e:
        logging.error("Error adding subtask to issue '%s' in Jira", parent)
        logging.debug(e)
        return -1

    try:
        if child is not None:
            jira.transition_issue(child, '21')
            logging.info("transitioned to 'In Progress'\n")
    except Exception, e:
        logging.error("Error transitioning subtask to issue '%s' in Jira", child)
        logging.debug(e)
        return -1
    print "Subtask:%s created and transitioned to In-progress" % child

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


# ----------------------------------------------------------------------------
# git helper functions
#
# Get our current branchname
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


if __name__ == "__main__":
    main()