__author__ = 'akbennett'
from ConfigParser import RawConfigParser
import os
import getpass

class Configuration(object):
    def __init__(self, filename):
        self.parser = RawConfigParser()
        filepath = os.path.expanduser(filename)
        if os.path.exists(filepath): self.parser.read(filepath)
        else:
            # Set up config file
            self.parser.add_section('jira_default')
            self.parser.set('jira_default', 'username', raw_input('username: '))
            passwd_confirmed = False
            passwd = None
            passwd2 = None
            while not passwd_confirmed:
                passwd = getpass.getpass('password: ')
                passwd2 = getpass.getpass('confirm: ')
                if passwd != passwd2: print 'passwords do not match.'
                else: passwd_confirmed = True
            self.parser.set('jira_default', 'password', passwd)
            self.parser.set('jira_default', 'host', raw_input('host (e.g jira.atlassian.com): '))
            self.parser.set('jira_default', 'path', '/rest/api/latest')
            # Color-coded statuses
            #self.parser.set('colors', 'Resolved', 'green')
            #self.parser.set('colors', 'In Progress', 'magenta')
            f = open(filepath, 'w')
            self.parser.write(f)
            os.chmod(filepath, 0600) #Only user can read this

    def get(self, section, key):
        return self.parser.get(section, key)

def default_config(config_filename):
    return Configuration(config_filename)

