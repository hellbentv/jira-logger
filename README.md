
# jira-logger.py

A custom jira tool for managing jira issues

# Prerequisites

You'll need python 2.7 and [pip](http://pypi.python.org/pypi/pip/) installed.

# Try it out

Clone the repo, and run:

	pip install -r requirements.txt

Run Help

    $ ./jira-log.py --help
    Common Commands
    ===============
     Show me the available epics / engineering cards
        ./jira-log.py --epic
     Add a comment and log 3 hours of work
        ./jira-log.py --issue LAVA-1608 --comment 'more work' --hours 3
     Create a new sub-task card under Blueprint LAVA-1590
        ./jira-log.py --createsubtask LAVA-1590 'New task research'
     Create a new blueprint under epic LAVA-1608
        ./jira-log.py --createblueprint LAVA-1608 'New task research'
    
    usage: jira-log.py [-h] [--user USER] [--inprogress] [--allmycards]
                       [--epics EPICS]
                       [--createsubtask CREATESUBTASK CREATESUBTASK]
                       [--createblueprint CREATEBLUEPRINT CREATEBLUEPRINT]
                       [--query QUERY] [--issue ISSUE] [--comment COMMENT]
                       [--hours HOURS] [--debug]
    
    This is a simple tool for logging work hours and adding comments to cards
    
    optional arguments:
      -h, --help            show this help message and exit
      --user USER, -u USER  Override the user in the queries
      --inprogress          Display only inprogress cards
      --allmycards          Display all cards
      --epics EPICS         Display all project Epics
      --createsubtask CREATESUBTASK CREATESUBTASK
                            [blueprint id] ['Summary string']
      --createblueprint CREATEBLUEPRINT CREATEBLUEPRINT
                            [epic id] ['Summary String']
      --query QUERY, -q QUERY
                            Display cards from custom Jira query
      --issue ISSUE, -i ISSUE
                            Issue # you wish to add a comment to and/or log hours
      --comment COMMENT, -c COMMENT
                            Comment to be added to the CARD
      --hours HOURS, -hour HOURS
                            log hours to the specified card
      --debug, -d

# Credentials

Credentials are stored in a plain-text config file in `~/.jira-log.rc` with `600` permissions, so they can only be read by you (similar to the approach that the `svn` command line client takes).

If you need to change the credentials or API details, just remove the `~/.jira-log.rc` file and next time you run a query you will be prompted to update it.

If you need to connect to multiple jira instances, it's probably easiest just to copy the cloned repo to another directory and run the second copy with your different credentials.

