
# -*- coding: utf-8 -*-

# This file is part of OpenHatch.
# Copyright (C) 2010 Parker Phinney
# Copyright (C) 2011 Krzysztof Tarnowski (krzysztof.tarnowski@ymail.com)
# Copyright (C) 2009, 2010, 2011 OpenHatch, Inc.
# Copyright (C) 2011 Jairo E. Lopez
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

from django.http import HttpResponse, \
        HttpResponseRedirect, HttpResponseServerError, HttpResponseBadRequest
from mysite.base.helpers import render_response
from django_authopenid.forms import OpenidSigninForm
import simplejson
from django.template import RequestContext, loader, Context
from django.core.urlresolvers import reverse
from django.contrib.auth.forms import AuthenticationForm

import mysite.profile as profile
import mysite.account
import mysite.profile.controllers
import mysite.account.forms
from mysite.base.decorators import view
import mysite.customs.feed
import mysite.search.controllers
import mysite.search.models
import mysite.missions.models 
from mysite.missions.models import Step, StepCompletion

import feedparser
import lxml.html
import random
import datetime

from django.contrib.auth.decorators import login_required

def front_page_data():
    data = {}
    data['entries'] = mysite.customs.feed.cached_blog_entries()[:1]
    feed_items = list(mysite.search.models.Answer.objects.order_by('-modified_date')[:5])
    feed_items.extend(mysite.search.models.WannaHelperNote.objects.order_by('-modified_date')[:5])
    feed_items.sort(key=lambda x: x.modified_date, reverse=True)
    data['recent_feed_items'] = feed_items[:5]
    return data

@view
def home(request):
    data = front_page_data()

    everybody = list(mysite.profile.models.Person.objects.exclude(link_person_tag=None))
    random.shuffle(everybody)
    data['random_profiles'] = everybody[0:5]

    if request.user.is_authenticated():
        template_path = 'base/landing_page_for_logged_in_users.html'
        # figure oout which nudges we want to show them
        person = request.user.get_profile()

        data['nudge_location'] = person.should_be_nudged_about_location()
        data['nudge_tags'] = not person.get_tags_for_recommendations()
        data['nudge_missions'] = not mysite.missions.models.StepCompletion.objects.filter(person=person)

        # Project editor nudging. Note:
        # If the person has some dias, then no nudge!
        if person.dataimportattempt_set.all():
            pass # whee, no nudge. the user has already seen the project editor.
        else:
            # So, either the person has some projects listed publicly, in which case,
            # we should remind the person just to use the importer...
            if person.get_published_portfolio_entries():
                data['nudge_importer_when_user_has_some_projects'
                     ] = True # just nudge about the importer...
            else:
                # the person has entered zero projects and hasn't touched the importer
                # so introduce him or her to use the importer!
                data['nudge_importer_when_user_has_no_projects'
                     ] = True # give the general project editing nudge

        data['show_nudge_box'] = (data['nudge_location'] or 
                'nudge_importer_when_user_has_no_projects' in data or data['nudge_tags'] or
                                  'nudge_importer_when_user_has_some_projects' in data)

        # Bug recommendations
        suggested_searches = request.user.get_profile().get_recommended_search_terms()
        recommender = mysite.profile.controllers.RecommendBugs(
            suggested_searches, n=5)

        if not recommender.is_cache_empty():
            data['recommended_bugs'] = list(recommender.recommend())
        else:
            # a dict pairing two things:
            # * GET data dicts (to be passed to Query's create_from_GET_data)
            # * strings of HTML representing the bug classification
            recommended_bug_string2GET_data_dicts = {
            "<strong>Bitesize</strong> bugs whose main project language is <strong>C</strong>":
                {u'language':u'C', u'toughness':u'bitesize'},
            "<strong>Bitesize</strong> bugs matching &lsquo;<strong>audio</strong>&rsquo;":
                {u'q':u'audio', u'toughness':u'bitesize'},
            "Bugs matching &lsquo;<strong>unicode</strong>&rsquo;":
                {u'q':u'unicode'},
            "Requests for <strong>documentation writing/editing</strong>":
                {u'contribution_type':u'documentation'},
            #"Requests for <strong>documentation writing/editing</strong>":
            #    {u'contribution_type':u'documentation'},
            }
            recommended_bug_string2Query_objects = {}
            for (string, GET_data_dict) in recommended_bug_string2GET_data_dicts.items():
                query = mysite.search.controllers.Query.create_from_GET_data(GET_data_dict)
                recommended_bug_string2Query_objects[string] = query

            data[u'recommended_bug_string2Query_objects'] = recommended_bug_string2Query_objects
        
        completed_missions = dict((c.step.name, True) for c in StepCompletion.objects.filter(person=request.user.get_profile()))
        data[u'completed_missions'] = completed_missions
        
        data[u'projects_i_wanna_help'] = person.projects_i_wanna_help.all()
        data[u'projects_i_helped'] = person.get_published_portfolio_entries()

        # These are for project maintainers
        data[u'projects_with_wannahelpers'] = [
            pfe.project for pfe in person.get_published_portfolio_entries()
            if pfe.project.wannahelpernote_set.all().count()]
        data[u'maintainer_nudges'] = maintainer_nudges = {}
        maintainer_nudges['show_project_page'] = (
            person.get_published_portfolio_entries() and
            not person.user.answer_set.all())
        maintainer_nudges[u'add_bug_tracker'] = (
            person.get_published_portfolio_entries() and
            (not any([pfe.project.bug_set.all()
                      for pfe in person.get_published_portfolio_entries()])))
    else: # no user logged in. Show front-page
        template_path = 'base/landing.html'
    
    return (request, template_path, data)

def page_to_js(request):
    # FIXME: In the future, use:
    # from django.template.loader import render_to_string
    # to generate html_doc
    html_doc = "<strong>zomg</strong>"
    encoded_for_js = simplejson.dumps(html_doc)
    # Note: using application/javascript as suggested by
    # http://www.ietf.org/rfc/rfc4329.txt
    return render_response(request, 'base/append_ourselves.js',
                              {'in_string': encoded_for_js},
                              mimetype='application/javascript')

def page_not_found(request):
    t = loader.get_template('404.html')
    c = Context({
        'user': request.user
    })

    response = HttpResponse(t.render(c), status=404)
    return response



def geocode(request):
    address = request.GET.get('address', None)
    if not address:
        return HttpResponseBadRequest() # no address :-(
    # try to geocode
    coordinates_as_json = mysite.base.controllers.cached_geocoding_in_json(address)
    if coordinates_as_json == 'null':
        # We couldn't geocode that.
        return HttpResponseBadRequest() # no address :-(
    return HttpResponse(coordinates_as_json, 
                        mimetype='application/json')

# Obtains meta data for request return
def meta_data():
    data = {}
    data['dia_diagnostics'] = {}

    # temp variable for shortness
    my = data['dia_diagnostics']
    
    my['Uncompleted DIAs'] = mysite.profile.models.DataImportAttempt.objects.filter(
        completed=False).count()

    one_minute_ago = (datetime.datetime.now() -
                      datetime.timedelta(minutes=1))

    my['Uncompleted DIAs older than 1 minute'] = mysite.profile.models.DataImportAttempt.objects.filter(
        completed=False, date_created__lt=one_minute_ago).count()

    five_minute_ago = (datetime.datetime.now() -
                      datetime.timedelta(minutes=5))

    my['Uncompleted DIAs older than 5 minutes'] = mysite.profile.models.DataImportAttempt.objects.filter(
        completed=False, date_created__lt=one_minute_ago).count()
        
    data['bug_diagnostics'] = {}
    # local name for shortness
    my = data['bug_diagnostics']

    one_hour_and_two_days_ago = (datetime.datetime.now() -
                                datetime.timedelta(days=2, hours=1))

    my['Bugs last polled more than than two days + one hour ago'] = mysite.search.models.Bug.all_bugs.filter(
        last_polled__lt=one_hour_and_two_days_ago).count()

    three_days_ago = (datetime.datetime.now() -
                    datetime.timedelta(days=3))
    my['Bugs last polled more than three days ago'] = mysite.search.models.Bug.all_bugs.filter(
        last_polled__lt=three_days_ago).count()

    # Test for 0 division
    allbug = mysite.search.models.Bug.all_bugs.count()
    perbug = 0.0
    if allbug:
        perbug = ( mysite.search.models.Bug.all_bugs.filter(
            last_polled__lt=three_days_ago).count() * 100.0 / allbug)

    my['Bugs last polled more than three days ago (in percent)'] = perbug

    return data

def meta_exit_code(data=None):
    if data is None:
        data = meta_data()

    # Temp variable for shortness
    my = data['bug_diagnostics']

    # More temp variables for shortness
    bug1 = my['Bugs last polled more than than two days + one hour ago']
    bug2 = my['Bugs last polled more than three days ago']
    perbug = my['Bugs last polled more than three days ago (in percent)']

    # Exit codes and stdout for Nagios integration
    if bug2:
        print "{0} - Polled 2+: {1} Polled 3+: {2} ({3}%)".format("CRITICAL", bug1, bug2, perbug)
        return 2 
    elif bug1:
        print "{0} - Polled 2+: {1} Polled 3+: {2} ({3}%)".format("WARNING", bug1, bug2, perbug)
        return 1
    else:
        print "{0} - Polled 2+: {1} Polled 3+: {2} ({3}%)".format("OK", bug1, bug2, perbug)
        return 0
        
@view
def meta(request):
    return (request, 'meta.html', meta_data())

@login_required
def save_portfolio_entry_ordering_do(request):
    from mysite.profile.models import PortfolioEntry

    list_of_ids = request.POST.getlist('sortable_portfolio_entry[]')
    are_we_archiving_yet = False
    for n, id in enumerate(list_of_ids):
        if id == 'FOLD': # ha not an id
            are_we_archiving_yet = True
            continue
        pfe = PortfolioEntry.objects.get(id=int(id), person__user=request.user)
        pfe.sort_order = -n # negated so we can sort descending
        pfe.is_archived = are_we_archiving_yet
        pfe.save()
    return HttpResponse('1')

@view
def landing_for_opp_hunters(request):
    return (request, 'landing_for_opp_hunters.html',
            front_page_data())

@view
def landing_for_project_maintainers(request):
    return (request, 'landing_for_project_maintainers.html',
            front_page_data())

@view
def landing_for_documenters(request):
    return (request, 'landing_for_documenters.html',
            front_page_data())

@login_required
def test_weekly_email_re_projects(request):
    from mysite.profile.management.commands import send_weekly_emails
    from mysite.profile.models import Person
    command = send_weekly_emails.Command()
    command.this_run_covers_things_since = datetime.datetime(2009, 5, 28)
    command.this_run_covers_things_up_until = datetime.datetime.utcnow()
    context = command.get_context_for_weekly_email_to(request.user.get_profile()) or {}
    if context:
        return mysite.base.decorators.as_view(request, 'weekly_email_re_projects.html', context, "test_weekly_email_re_projects")
    else:
        return HttpResponse("(We couldn't find any recent project activity for you, so you wouldn't get an email updating you about it.)")
