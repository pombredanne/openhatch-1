# This file is part of OpenHatch.
# Copyright (C) 2010 Jack Grigg
# Copyright (C) 2010 OpenHatch, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import urllib2

import gdata.client

from django.core.management.base import BaseCommand

import django.conf
django.conf.settings.CELERY_ALWAYS_EAGER = True

import mysite.customs.mechanize_helpers

import mysite.customs.bugtrackers.bugzilla
import mysite.customs.bugtrackers.launchpad
import mysite.customs.bugtrackers.roundup
import mysite.customs.bugtrackers.trac

### All this code runs synchronously once a day.
### For now, we can crawl all the bug trackers in serial.

### One day, though, we will crawl so many bug trackers that it will take
### too long.

### I suggest that, at that point, we fork a number of worker processes, and
### turn these lists into a queue or something. That should be easy with the
### multiprocessing module. Then we can do N at once.

### We could do something smart with statistics, detecting the average
### refresh time within the bug tracker of a bug, then polling at some
### approximation of that rate. (But, really, why bother?)

### Since most of the time we're waiting on the network, we could also use
### Twisted or Stackless Python or something. That would be super cool, too.
### If somone can show me how to migrate this codebase to it, that'd be neat.
### I'm unlikely to look into it myself, though.
###
### ### UPDATE: We now have an asynchronous bug importer based on Twisted. It
### ### will eventually handle all bug importing, making this file obsolete.
### ### And it didn't even take a year!
### ### -- Jack - 2011-04-16

### (If at some point we start indexing absolutely every bug in free and open
### source software, then the above ideas will actually become meaningful.)

### -- New Age Asheesh, 2010-05-31.

class Command(BaseCommand):
    args = '<tracker_type tracker_type ...> <ohloh>'
    help = """Call this once a day to make sure we run Bug search-related nightly jobs.
If argument(s) are supplied, only the corresponding functions are run.
With no arguments, all importers and the Ohloh broken link expunger are run.

Supported tracker types:
 * roundup
 * trac
 * bugzilla
 * launchpad"""

    def find_and_update_enabled_roundup_trackers(self):
        enabled_roundup_trackers = []

        ### First, the "find" step
        for thing_name in dir(mysite.customs.bugtrackers.roundup):
            thing = getattr(mysite.customs.bugtrackers.roundup,
                            thing_name)
            if hasattr(thing, 'enabled'):
                if getattr(thing, 'enabled'):
                    enabled_roundup_trackers.append(thing)

        ### Okay, now update!
        for thing in enabled_roundup_trackers:
            instantiated = thing()
            project_name = instantiated.project.name
            logging.info("[Roundup] About to update bugs from project named %s." % project_name)
            try:
                instantiated.update()
            except urllib2.URLError, e:
                logging.error("[Roundup] ERROR: %s importer failed with urllib2.URLError, skipping..." % project_name)
                logging.error("[Roundup] Error message: %s" % str(e))

    def find_and_update_enabled_trac_instances(self):
        enabled_trac_instances = []

        ### First, the "find" step
        for thing_name in dir(mysite.customs.bugtrackers.trac):
            thing = getattr(mysite.customs.bugtrackers.trac,
                            thing_name)
            if hasattr(thing, 'enabled'):
                if getattr(thing, 'enabled'):
                    enabled_trac_instances.append(thing)

        ### Okay, now update!
        for thing in enabled_trac_instances:
            instantiated = thing()
            tracker_name = instantiated.tracker_name
            logging.info("[Trac] About to update bugs from project named %s." % tracker_name)
            try:
                instantiated.update()
            except urllib2.URLError, e:
                logging.error("[Trac] ERROR: %s importer failed with urllib2.URLError, skipping..." % tracker_name)
                logging.error("[Trac] Error message: %s" % str(e))

    def find_and_update_enabled_bugzilla_instances(self):
        enabled_bugzilla_instances = []

        ### First, the "find" step
        for thing_name in dir(mysite.customs.bugtrackers.bugzilla):
            thing = getattr(mysite.customs.bugtrackers.bugzilla,
                            thing_name)
            if hasattr(thing, 'enabled'):
                if getattr(thing, 'enabled'):
                    enabled_bugzilla_instances.append(thing)

        ### Okay, now update!
        for thing in enabled_bugzilla_instances:
            instantiated = thing()
            tracker_name = instantiated.tracker_name
            logging.info("[Bugzilla] About to update bugs from project named %s." % tracker_name)
            # FIXME: The Bugzilla trackers seem to throw error 500 a lot.
            # For now, chuck in a dirty big try except to stop importer
            # breaking.
            try:
                instantiated.update()
            except urllib2.URLError, e:
                logging.error("[Bugzilla] ERROR: %s importer failed with urllib2.URLError, skipping..." % tracker_name)
                logging.error("[Bugzilla] Error message: %s" % str(e))

    def update_launchpad_hosted_projects(self):
        ### For Launchpad:
        # First, we ask the projects' bug trackers if there are new bugs we should know about
        mysite.customs.bugtrackers.launchpad.refresh_bugs_from_all_indexed_launchpad_projects()
        # Second, we go through our *own* database of Launchpad-sourced bugs, and make sure they are all up to date
        mysite.customs.bugtrackers.launchpad.refresh_all_launchpad_bugs()

    def check_for_broken_ohloh_links(self):
        for citation in mysite.profile.models.Citation.untrashed.filter(
            data_import_attempt__source__in=('oh', 'rs')):
            # check citation URL for being a 404
            # if so, remove set the URL to None. Also, log it.
            if citation.url:
                if mysite.customs.mechanize_helpers.link_works(citation.url):
                    # then we do nothing
                    pass
                else:
                    # aww shucks, I guess we have to remove it.
                    logging.warning("We had to remove the url %s from the citation whose PK is %d" % (
                        citation.url, citation.pk))
                    citation.url = None
                    citation.save()

    def handle(self, *args, **options):
        cdt_fns = {
                'ohloh': self.check_for_broken_ohloh_links,
                'trac': self.find_and_update_enabled_trac_instances,
                'roundup': self.find_and_update_enabled_roundup_trackers,
                'bugzilla': self.find_and_update_enabled_bugzilla_instances,
                'launchpad': self.update_launchpad_hosted_projects
                }
        ## Which ones do we plan to do this, time we run?
        # Well, if the user supplied arguments on the command line, then put those in the list.
        if args:
            tasks = args
        else:
            # Plan to do them all, since the user did not sub-specify.
            tasks = cdt_fns.keys()

        # Okay, so do the work.
        for key in tasks:
            cdt_fns[key]()
